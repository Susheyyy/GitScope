from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ContributorStats(BaseModel):
    name: str
    email: str
    commits: int
    lines_added: int
    lines_deleted: int
    ownership_percentage: float = Field(description="Percentage of commits authored by this person in the scope")


class HotspotItem(BaseModel):
    path: str
    is_directory: bool = False
    is_deleted: bool = False
    commits: int
    lines_added: int
    lines_deleted: int
    total_churn: int
    top_contributors: List[ContributorStats] = Field(default_factory=list)
    bus_factor: int = 1
    risk_level: str = "Low"


class AuthorProfile(BaseModel):
    name: str
    email: str
    total_commits: int
    lines_added: int
    lines_deleted: int
    total_churn: int
    first_commit: Optional[datetime] = None
    last_commit: Optional[datetime] = None
    primary_directories: List[str] = Field(default_factory=list)
    primary_files: List[str] = Field(default_factory=list)
    summary: str = ""


class CoupledPair(BaseModel):
    file_a: str
    file_b: str
    together_commits: int
    total_commits_a: int
    total_commits_b: int
    coupling_percentage: float


class CommitHygieneIssue(BaseModel):
    commit_hash: str
    author_name: str
    message: str
    issue_type: str
    details: str


class CommitHygieneReport(BaseModel):
    quality_score: int = Field(description="Score from 0 to 100", default=100)
    total_scanned: int = 0
    vague_commits_count: int = 0
    dump_commits_count: int = 0
    ticket_referenced_count: int = 0
    issues: List[CommitHygieneIssue] = Field(default_factory=list)


class ScopeReport(BaseModel):
    repo_name: str
    repo_path: str
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    since: Optional[str] = None
    until: Optional[str] = None
    total_commits: int
    total_authors: int
    contributors: List[AuthorProfile] = Field(default_factory=list)
    hotspots_files: List[HotspotItem] = Field(default_factory=list)
    hotspots_directories: List[HotspotItem] = Field(default_factory=list)
    coupled_files: List[CoupledPair] = Field(default_factory=list)
    hygiene: CommitHygieneReport = Field(default_factory=CommitHygieneReport)
