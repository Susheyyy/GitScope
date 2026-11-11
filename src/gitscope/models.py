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
    commits: int
    lines_added: int
    lines_deleted: int
    total_churn: int
    top_contributors: List[ContributorStats] = Field(default_factory=list)
    bus_factor: int = 1
    risk_level: str = "Low"


class ScopeReport(BaseModel):
    repo_name: str
    repo_path: str
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    since: Optional[str] = None
    until: Optional[str] = None
    total_commits: int
    total_authors: int
    hotspots_files: List[HotspotItem] = Field(default_factory=list)
    hotspots_directories: List[HotspotItem] = Field(default_factory=list)
