from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from models import (
    AuthorProfile,
    CommitHygieneIssue,
    CommitHygieneReport,
    ContributorChangeItem,
    ContributorHygieneStats,
    ContributorStats,
    CoupledPair,
    HotspotItem,
    ScopeReport,
)
from parser import CommitRecord

VAGUE_MESSAGE_PATTERNS = [
    r"^(fix|fixes|fixed)$",
    r"^(update|updates|updated)$",
    r"^(wip|work in progress)$",
    r"^(changes|change)$",
    r"^(asdf|test|testing|foo|bar)$",
    r"^(cleanup|clean up)$",
    r"^(misc|minor|stuff)$",
    r"^(commit|save)$",
    r"^(\.)$",
    r"^(ui fix|ui fixes|bug fix|bug fixes|quick fix|hotfix)$",
    r"^(small changes|minor changes|more changes|few fixes)$",
]
TICKET_REGEX = re.compile(r"([A-Z]{2,10}-\d+|#\d+)")
CONVENTIONAL_COMMIT_REGEX = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-\./]+\))?:\s+.+",
    re.IGNORECASE,
)


class AnalysisEngine:
    def __init__(
        self,
        repo_name: str,
        repo_path: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        existing_files: Optional[Set[str]] = None,
    ):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.since = since
        self.until = until
        self.existing_files = existing_files or set()
        self._vague_regexes = [re.compile(p, re.IGNORECASE) for p in VAGUE_MESSAGE_PATTERNS]

    @staticmethod
    def _calculate_bus_factor(contributors: List[ContributorStats], threshold: float = 0.8) -> int:
        if not contributors:
            return 0
        sorted_contribs = sorted(contributors, key=lambda c: c.ownership_percentage, reverse=True)
        accumulated = 0.0
        count = 0
        for c in sorted_contribs:
            accumulated += c.ownership_percentage
            count += 1
            if accumulated >= threshold:
                break
        return max(count, 1)

    @staticmethod
    def _evaluate_risk(total_churn: int, bus_factor: int, churn_p75: float) -> str:
        if total_churn >= churn_p75 and bus_factor == 1:
            return "High"
        elif total_churn >= churn_p75 or bus_factor == 1:
            return "Medium"
        return "Low"

    @staticmethod
    def _generate_author_summary(
        name: str,
        total_commits: int,
        added: int,
        deleted: int,
        top_dirs: List[str],
        top_files: List[str],
    ) -> str:
        churn = added + deleted
        files_str = ", ".join(f"`{Path(f).name}`" for f in top_files[:3]) if top_files else "none"
        dirs_str = ", ".join(f"`{d}`" for d in top_dirs[:2]) if top_dirs else "root"
        return (
            f"Authored {total_commits} commit{'s' if total_commits != 1 else ''} with {churn} lines modified "
            f"(+{added}/-{deleted}). Focused primarily on {dirs_str}, mainly editing {files_str}."
        )

    def analyze(self, commits: Iterable[CommitRecord]) -> ScopeReport:
        rename_parent: Dict[str, str] = {}

        def find_canonical(path: str) -> str:
            curr = path
            visited = set()
            while curr in rename_parent and curr not in visited:
                visited.add(curr)
                curr = rename_parent[curr]
            return curr

        raw_file_commits: Dict[str, Set[str]] = defaultdict(set)
        raw_file_added: Dict[str, int] = defaultdict(int)
        raw_file_deleted: Dict[str, int] = defaultdict(int)
        raw_file_authors: Dict[str, Dict[str, Dict[str, any]]] = defaultdict(
            lambda: defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0, "name": ""})
        )

        dir_commits: Dict[str, Set[str]] = defaultdict(set)
        dir_added: Dict[str, int] = defaultdict(int)
        dir_deleted: Dict[str, int] = defaultdict(int)
        dir_authors: Dict[str, Dict[str, Dict[str, any]]] = defaultdict(
            lambda: defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0, "name": ""})
        )

        author_summary: Dict[str, Dict[str, any]] = defaultdict(
            lambda: {
                "name": "",
                "commits": 0,
                "added": 0,
                "deleted": 0,
                "first_commit": None,
                "last_commit": None,
                "dirs": defaultdict(int),
                "files": defaultdict(int),
                "change_log": [],
                "conventional_count": 0,
                "vague_count": 0,
            }
        )

        co_change_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        all_commit_hashes: Set[str] = set()
        all_authors: Set[str] = set()

        hygiene_issues: List[CommitHygieneIssue] = []
        vague_count = 0
        conventional_count = 0
        ticket_count = 0

        for commit in commits:
            all_commit_hashes.add(commit.hash)
            for a in commit.authors:
                all_authors.add(a.email)

            stripped_msg = commit.message.strip()
            is_conventional = bool(CONVENTIONAL_COMMIT_REGEX.match(stripped_msg))
            if is_conventional:
                conventional_count += 1

            is_vague = False
            if not is_conventional:
                is_vague = any(r.match(stripped_msg) for r in self._vague_regexes) or len(stripped_msg) <= 4

            if is_vague:
                vague_count += 1
                hygiene_issues.append(
                    CommitHygieneIssue(
                        commit_hash=commit.hash[:8],
                        author_name=commit.author_name,
                        message=commit.message,
                        issue_type="Vague Message",
                        details=f"Subject '{commit.message}' provides no context on what was changed or why",
                    )
                )

            if TICKET_REGEX.search(commit.message):
                ticket_count += 1

            unique_files_in_commit = set()
            commit_files_list = []
            commit_lines_added = 0
            commit_lines_deleted = 0

            for change in commit.changes:
                if change.old_path:
                    rename_parent[change.old_path] = change.path

                f_path = change.path
                unique_files_in_commit.add(f_path)
                commit_files_list.append(f_path)
                commit_lines_added += change.added
                commit_lines_deleted += change.deleted

                raw_file_commits[f_path].add(commit.hash)
                raw_file_added[f_path] += change.added
                raw_file_deleted[f_path] += change.deleted

                credit_share = 1.0 / len(commit.authors) if commit.authors else 1.0

                for author in commit.authors:
                    f_auth = raw_file_authors[f_path][author.email]
                    f_auth["name"] = author.name
                    f_auth["commits"] += credit_share
                    f_auth["added"] += int(change.added * credit_share)
                    f_auth["deleted"] += int(change.deleted * credit_share)

            if len(unique_files_in_commit) <= 30:
                canonical_unique = {find_canonical(p) for p in unique_files_in_commit}
                for f1, f2 in combinations(sorted(canonical_unique), 2):
                    co_change_counts[(f1, f2)] += 1

            dirs_touched_in_commit = {
                (
                    str(Path(find_canonical(c.path)).parent).replace("\\", "/")
                    if str(Path(find_canonical(c.path)).parent).replace("\\", "/") != "."
                    else "root"
                )
                for c in commit.changes
            }
            credit_share = 1.0 / len(commit.authors) if commit.authors else 1.0

            for d_name in dirs_touched_in_commit:
                dir_commits[d_name].add(commit.hash)
                for author in commit.authors:
                    d_auth = dir_authors[d_name][author.email]
                    d_auth["name"] = author.name
                    d_auth["commits"] += credit_share

            for change in commit.changes:
                canonical_p = find_canonical(change.path)
                c_dir = (
                    str(Path(canonical_p).parent).replace("\\", "/")
                    if str(Path(canonical_p).parent).replace("\\", "/") != "."
                    else "root"
                )
                dir_added[c_dir] += change.added
                dir_deleted[c_dir] += change.deleted

                for author in commit.authors:
                    prof = author_summary[author.email]
                    prof["name"] = author.name
                    prof["added"] += int(change.added * credit_share)
                    prof["deleted"] += int(change.deleted * credit_share)
                    prof["dirs"][c_dir] += 1
                    prof["files"][canonical_p] += 1

            for author in commit.authors:
                prof = author_summary[author.email]
                prof["name"] = author.name
                prof["commits"] += 1
                if is_conventional:
                    prof["conventional_count"] += 1
                if is_vague:
                    prof["vague_count"] += 1
                if not prof["first_commit"] or commit.timestamp < prof["first_commit"]:
                    prof["first_commit"] = commit.timestamp
                if not prof["last_commit"] or commit.timestamp > prof["last_commit"]:
                    prof["last_commit"] = commit.timestamp

                prof["change_log"].append(
                    ContributorChangeItem(
                        commit_hash=commit.hash[:8],
                        timestamp=commit.timestamp,
                        message=commit.message,
                        lines_added=commit_lines_added,
                        lines_deleted=commit_lines_deleted,
                        files_changed=commit_files_list[:8],
                    )
                )

        file_commits: Dict[str, Set[str]] = defaultdict(set)
        file_added: Dict[str, int] = defaultdict(int)
        file_deleted: Dict[str, int] = defaultdict(int)
        file_authors: Dict[str, Dict[str, Dict[str, any]]] = defaultdict(
            lambda: defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0, "name": ""})
        )

        for path in list(raw_file_commits.keys()):
            canonical = find_canonical(path)
            file_commits[canonical].update(raw_file_commits[path])
            file_added[canonical] += raw_file_added[path]
            file_deleted[canonical] += raw_file_deleted[path]

            for email, stats in raw_file_authors[path].items():
                target = file_authors[canonical][email]
                target["name"] = stats["name"]
                target["commits"] += stats["commits"]
                target["added"] += stats["added"]
                target["deleted"] += stats["deleted"]

        file_items: List[HotspotItem] = []
        for path, c_set in file_commits.items():
            churn = file_added[path] + file_deleted[path]
            total_file_commits = len(c_set)

            contribs: List[ContributorStats] = []
            for email, stats in file_authors[path].items():
                ownership = (stats["commits"] / total_file_commits) if total_file_commits > 0 else 0.0
                contribs.append(
                    ContributorStats(
                        name=stats["name"],
                        email=email,
                        commits=int(round(stats["commits"])),
                        lines_added=stats["added"],
                        lines_deleted=stats["deleted"],
                        ownership_percentage=round(ownership, 4),
                    )
                )
            contribs.sort(key=lambda c: c.ownership_percentage, reverse=True)
            bf = self._calculate_bus_factor(contribs)

            is_deleted = (path not in self.existing_files) if self.existing_files else False

            file_items.append(
                HotspotItem(
                    path=path,
                    is_directory=False,
                    is_deleted=is_deleted,
                    commits=total_file_commits,
                    lines_added=file_added[path],
                    lines_deleted=file_deleted[path],
                    total_churn=churn,
                    top_contributors=contribs[:5],
                    bus_factor=bf,
                )
            )

        dir_items: List[HotspotItem] = []
        for d_path, c_set in dir_commits.items():
            churn = dir_added[d_path] + dir_deleted[d_path]
            total_dir_commits = len(c_set)

            contribs: List[ContributorStats] = []
            for email, stats in dir_authors[d_path].items():
                ownership = (stats["commits"] / total_dir_commits) if total_dir_commits > 0 else 0.0
                contribs.append(
                    ContributorStats(
                        name=stats["name"],
                        email=email,
                        commits=int(round(stats["commits"])),
                        lines_added=stats["added"],
                        lines_deleted=stats["deleted"],
                        ownership_percentage=min(round(ownership, 4), 1.0),
                    )
                )
            contribs.sort(key=lambda c: c.ownership_percentage, reverse=True)
            bf = self._calculate_bus_factor(contribs)

            dir_items.append(
                HotspotItem(
                    path=d_path,
                    is_directory=True,
                    commits=total_dir_commits,
                    lines_added=dir_added[d_path],
                    lines_deleted=dir_deleted[d_path],
                    total_churn=churn,
                    top_contributors=contribs[:5],
                    bus_factor=bf,
                )
            )

        file_items.sort(key=lambda item: (not item.is_deleted, item.commits, item.total_churn), reverse=True)
        dir_items.sort(key=lambda item: (item.commits, item.total_churn), reverse=True)

        if file_items:
            churn_values = sorted([f.total_churn for f in file_items])
            p75_idx = int(len(churn_values) * 0.75)
            churn_p75 = churn_values[min(p75_idx, len(churn_values) - 1)]
            for f in file_items:
                f.risk_level = self._evaluate_risk(f.total_churn, f.bus_factor, churn_p75)

        if dir_items:
            dir_churn_values = sorted([d.total_churn for d in dir_items])
            p75_idx = int(len(dir_churn_values) * 0.75)
            dir_p75 = dir_churn_values[min(p75_idx, len(dir_churn_values) - 1)]
            for d in dir_items:
                d.risk_level = self._evaluate_risk(d.total_churn, d.bus_factor, dir_p75)

        contributor_profiles: List[AuthorProfile] = []
        for email, prof in author_summary.items():
            top_dirs = [d[0] for d in sorted(prof["dirs"].items(), key=lambda x: x[1], reverse=True)[:3]]
            top_files = [f[0] for f in sorted(prof["files"].items(), key=lambda x: x[1], reverse=True)[:3]]
            summary_text = self._generate_author_summary(
                prof["name"], prof["commits"], prof["added"], prof["deleted"], top_dirs, top_files
            )

            c_total = prof["commits"]
            v_count = prof["vague_count"]
            conv_count = prof["conventional_count"]
            author_score = 100
            if c_total > 0:
                author_score = max(0, 100 - int((v_count / c_total) * 70))
                if conv_count == c_total:
                    author_score = 100

            contributor_profiles.append(
                AuthorProfile(
                    name=prof["name"],
                    email=email,
                    total_commits=prof["commits"],
                    lines_added=prof["added"],
                    lines_deleted=prof["deleted"],
                    total_churn=prof["added"] + prof["deleted"],
                    first_commit=prof["first_commit"],
                    last_commit=prof["last_commit"],
                    primary_directories=top_dirs,
                    primary_files=top_files,
                    summary=summary_text,
                    change_log=prof["change_log"][:30],
                    hygiene=ContributorHygieneStats(
                        conventional_count=conv_count,
                        vague_count=v_count,
                        hygiene_score=author_score,
                    ),
                )
            )
        contributor_profiles.sort(key=lambda x: x.total_commits, reverse=True)

        coupled_pairs: List[CoupledPair] = []
        for (f1, f2), together_count in co_change_counts.items():
            if together_count >= 2:
                c1 = len(file_commits.get(f1, set()))
                c2 = len(file_commits.get(f2, set()))
                if c1 > 0 and c2 > 0:
                    pct = round((together_count / min(c1, c2)) * 100, 1)
                    if pct >= 30.0:
                        coupled_pairs.append(
                            CoupledPair(
                                file_a=f1,
                                file_b=f2,
                                together_commits=together_count,
                                total_commits_a=c1,
                                total_commits_b=c2,
                                coupling_percentage=pct,
                            )
                        )
        coupled_pairs.sort(key=lambda cp: (cp.together_commits, cp.coupling_percentage), reverse=True)

        total_scanned = len(all_commit_hashes)
        penalty = 0
        conventional_pct = round((conventional_count / total_scanned) * 100, 1) if total_scanned > 0 else 0.0

        if total_scanned > 0:
            penalty += int((vague_count / total_scanned) * 60)
            if conventional_pct < 50.0:
                penalty += int((1.0 - (conventional_pct / 100.0)) * 20)

        quality_score = max(0, 100 - penalty)

        hygiene_report = CommitHygieneReport(
            quality_score=quality_score,
            total_scanned=total_scanned,
            conventional_count=conventional_count,
            conventional_percentage=conventional_pct,
            vague_commits_count=vague_count,
            ticket_referenced_count=ticket_count,
            issues=hygiene_issues[:20],
        )

        return ScopeReport(
            repo_name=self.repo_name,
            repo_path=self.repo_path,
            since=self.since,
            until=self.until,
            total_commits=len(all_commit_hashes),
            total_authors=len(all_authors),
            contributors=contributor_profiles,
            hotspots_files=file_items,
            hotspots_directories=dir_items,
            coupled_files=coupled_pairs,
            hygiene=hygiene_report,
        )
