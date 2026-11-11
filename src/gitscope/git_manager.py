from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class GitRepoManager:
    def __init__(self, target: str, cache_dir: Optional[Path] = None):
        self.target = target
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "gitscope_repos"
        self.is_remote = self._check_is_remote(target)
        self.repo_path: Optional[Path] = None

    @staticmethod
    def _check_is_remote(target: str) -> bool:
        parsed = urlparse(target)
        return parsed.scheme in ("http", "https") or target.startswith("git@")

    def prepare(self) -> Path:
        if not self.is_remote:
            local_path = Path(self.target).resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"Local repository path does not exist: {self.target}")
            if not (local_path / ".git").exists():
                raise ValueError(f"Path is not a valid Git repository (missing .git): {self.target}")
            self.repo_path = local_path
            return self.repo_path

        self._validate_remote_url(self.target)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        repo_name = Path(urlparse(self.target).path).stem.replace(".git", "")
        dest = self.cache_dir / repo_name

        if (dest / ".git").exists():
            subprocess.run(
                ["git", "-C", str(dest), "fetch", "--prune"],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            cmd = ["git", "clone", "--filter=blob:none", self.target, str(dest)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to clone repository: {result.stderr.strip()}")

        self.repo_path = dest
        return self.repo_path

    @staticmethod
    def _validate_remote_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}. Only HTTPS/HTTP are supported.")
        if not parsed.netloc:
            raise ValueError(f"Invalid repository URL: {url}")
