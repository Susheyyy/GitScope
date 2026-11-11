from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional


KNOWN_BOT_PATTERNS = [
    r"\[bot\]",
    r"dependabot",
    r"renovate",
    r"greenkeeper",
    r"snyk-bot",
    r"github-actions",
]

DEFAULT_IGNORED_EXTENSIONS = {
    ".lock", ".min.js", ".min.css", ".map", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"
}
DEFAULT_IGNORED_PATHS = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "Gemfile.lock"
}


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int


@dataclass
class CommitRecord:
    hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    changes: List[FileChange] = field(default_factory=list)


class GitLogParser:
    def __init__(
        self,
        repo_path: Path,
        since: Optional[str] = None,
        until: Optional[str] = None,
        filter_bots: bool = True,
    ):
        self.repo_path = repo_path
        self.since = since
        self.until = until
        self.filter_bots = filter_bots
        self._bot_regexes = [re.compile(p, re.IGNORECASE) for p in KNOWN_BOT_PATTERNS]

    def _is_bot(self, name: str, email: str) -> bool:
        if not self.filter_bots:
            return False
        for regex in self._bot_regexes:
            if regex.search(name) or regex.search(email):
                return True
        return False

    def _is_ignored_file(self, file_path: str) -> bool:
        path_obj = Path(file_path)
        if path_obj.name in DEFAULT_IGNORED_PATHS:
            return True
        if path_obj.suffix.lower() in DEFAULT_IGNORED_EXTENSIONS:
            return True
        parts = set(path_obj.parts)
        if any(ignored in parts for ignored in ("vendor", "node_modules", "dist", "build", ".git")):
            return True
        return False

    def parse_commits(self) -> Iterator[CommitRecord]:
        format_spec = "%x1e%H%x1f%aN%x1f%aE%x1f%at%x1f%s"
        cmd = [
            "git",
            "-C",
            str(self.repo_path),
            "log",
            f"--format={format_spec}",
            "--numstat",
            "--no-merges",
            "-M",
        ]

        if self.since:
            cmd.append(f"--since={self.since}")
        if self.until:
            cmd.append(f"--until={self.until}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        current_commit: Optional[CommitRecord] = None

        if not process.stdout:
            return

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            if line.startswith("\x1e"):
                if current_commit and not self._is_bot(current_commit.author_name, current_commit.author_email):
                    yield current_commit

                parts = line[1:].split("\x1f")
                if len(parts) >= 5:
                    c_hash, author_name, author_email, epoch_str, msg = parts[0], parts[1], parts[2], parts[3], parts[4]
                    try:
                        timestamp = datetime.utcfromtimestamp(int(epoch_str))
                    except (ValueError, TypeError):
                        timestamp = datetime.utcnow()

                    current_commit = CommitRecord(
                        hash=c_hash,
                        author_name=author_name,
                        author_email=author_email.lower(),
                        timestamp=timestamp,
                        message=msg,
                        changes=[],
                    )
                else:
                    current_commit = None
            elif current_commit:
                stat_parts = line.split("\t")
                if len(stat_parts) == 3:
                    added_str, deleted_str, raw_path = stat_parts
                    added = int(added_str) if added_str.isdigit() else 0
                    deleted = int(deleted_str) if deleted_str.isdigit() else 0

                    file_path = raw_path
                    if " => " in file_path:
                        match = re.search(r"(?:\{.* => (.*)\}|.* => (.*))", file_path)
                        if match:
                            file_path = match.group(1) or match.group(2)
                            file_path = re.sub(r"[{}\s]", "", file_path)

                    if not self._is_ignored_file(file_path):
                        current_commit.changes.append(
                            FileChange(path=file_path, added=added, deleted=deleted)
                        )

        if current_commit and not self._is_bot(current_commit.author_name, current_commit.author_email):
            yield current_commit

        process.wait()
