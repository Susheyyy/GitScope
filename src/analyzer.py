from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from models import AuthorProfile, ContributorStats, HotspotItem, ScopeReport
from parser import CommitRecord


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
            }
        )

        all_commit_hashes: Set[str] = set()
        all_authors: Set[str] = set()

        for commit in commits:
            all_commit_hashes.add(commit.hash)
            for a in commit.authors:
                all_authors.add(a.email)

            for change in commit.changes:
                if change.old_path:
                    rename_parent[change.old_path] = change.path

                f_path = change.path
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
                if not prof["first_commit"] or commit.timestamp < prof["first_commit"]:
                    prof["first_commit"] = commit.timestamp
                if not prof["last_commit"] or commit.timestamp > prof["last_commit"]:
                    prof["last_commit"] = commit.timestamp

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

        # Build Contributor Profiles
        contributor_profiles: List[AuthorProfile] = []
        for email, prof in author_summary.items():
            top_dirs = [d[0] for d in sorted(prof["dirs"].items(), key=lambda x: x[1], reverse=True)[:3]]
            top_files = [f[0] for f in sorted(prof["files"].items(), key=lambda x: x[1], reverse=True)[:3]]
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
                )
            )
        contributor_profiles.sort(key=lambda x: x.total_commits, reverse=True)

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
        )
