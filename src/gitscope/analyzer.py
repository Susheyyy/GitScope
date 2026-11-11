from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set

from gitscope.models import ContributorStats, HotspotItem, ScopeReport
from gitscope.parser import CommitRecord


class AnalysisEngine:
    def __init__(self, repo_name: str, repo_path: str, since: str = None, until: str = None):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.since = since
        self.until = until

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
        file_commits: Dict[str, Set[str]] = defaultdict(set)
        file_added: Dict[str, int] = defaultdict(int)
        file_deleted: Dict[str, int] = defaultdict(int)
        file_authors: Dict[str, Dict[str, Dict[str, any]]] = defaultdict(
            lambda: defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0, "name": ""})
        )

        dir_commits: Dict[str, Set[str]] = defaultdict(set)
        dir_added: Dict[str, int] = defaultdict(int)
        dir_deleted: Dict[str, int] = defaultdict(int)
        dir_authors: Dict[str, Dict[str, Dict[str, any]]] = defaultdict(
            lambda: defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0, "name": ""})
        )

        all_commit_hashes: Set[str] = set()
        all_authors: Set[str] = set()

        for commit in commits:
            all_commit_hashes.add(commit.hash)
            all_authors.add(commit.author_email)

            for change in commit.changes:
                f_path = change.path
                norm_dir = str(Path(f_path).parent).replace("\\", "/")
                if norm_dir == ".":
                    norm_dir = "root"

                file_commits[f_path].add(commit.hash)
                file_added[f_path] += change.added
                file_deleted[f_path] += change.deleted

                f_auth = file_authors[f_path][commit.author_email]
                f_auth["name"] = commit.author_name
                f_auth["commits"] += 1
                f_auth["added"] += change.added
                f_auth["deleted"] += change.deleted

                dir_commits[norm_dir].add(commit.hash)
                dir_added[norm_dir] += change.added
                dir_deleted[norm_dir] += change.deleted

                d_auth = dir_authors[norm_dir][commit.author_email]
                d_auth["name"] = commit.author_name
                d_auth["commits"] += 1
                d_auth["added"] += change.added
                d_auth["deleted"] += change.deleted

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
                        commits=stats["commits"],
                        lines_added=stats["added"],
                        lines_deleted=stats["deleted"],
                        ownership_percentage=round(ownership, 4),
                    )
                )
            contribs.sort(key=lambda c: c.commits, reverse=True)
            bf = self._calculate_bus_factor(contribs)

            file_items.append(
                HotspotItem(
                    path=path,
                    is_directory=False,
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
                        commits=stats["commits"],
                        lines_added=stats["added"],
                        lines_deleted=stats["deleted"],
                        ownership_percentage=round(ownership, 4),
                    )
                )
            contribs.sort(key=lambda c: c.commits, reverse=True)
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

        file_items.sort(key=lambda item: (item.commits, item.total_churn), reverse=True)
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

        return ScopeReport(
            repo_name=self.repo_name,
            repo_path=self.repo_path,
            since=self.since,
            until=self.until,
            total_commits=len(all_commit_hashes),
            total_authors=len(all_authors),
            hotspots_files=file_items,
            hotspots_directories=dir_items,
        )
