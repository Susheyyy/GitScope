from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


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

CO_AUTHOR_REGEX = re.compile(r"Co-authored-by:\s*([^<]+)<([^>]+)>", re.IGNORECASE)


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int
    old_path: Optional[str] = None


@dataclass
class AuthorInfo:
    name: str
    email: str


@dataclass
class CommitRecord:
    hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    authors: List[AuthorInfo] = field(default_factory=list)
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

    @staticmethod
    def _parse_rename_paths(raw_path: str) -> Tuple[str, Optional[str]]:
        if " => " not in raw_path:
            return raw_path, None

        if "{" in raw_path and "}" in raw_path:
            prefix = raw_path[: raw_path.index("{")]
            suffix = raw_path[raw_path.index("}") + 1 :]
            curly_content = raw_path[raw_path.index("{") + 1 : raw_path.index("}")]
            old_mid, new_mid = curly_content.split(" => ", 1)
            old_p = f"{prefix}{old_mid}{suffix}".replace("//", "/")
            new_p = f"{prefix}{new_mid}{suffix}".replace("//", "/")
            return new_p.strip(), old_p.strip()

        old_p, new_p = raw_path.split(" => ", 1)
        return new_p.strip(), old_p.strip()

    def parse_commits(self) -> Iterator[CommitRecord]:
        format_spec = "%x1e%H%x1f%aN%x1f%aE%x1f%at%x1f%s%x1f%b"
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

        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            if line.startswith("\x1e"):
                if current_commit and not self._is_bot(current_commit.author_name, current_commit.author_email):
                    yield current_commit

                parts = line[1:].split("\x1f")
                if len(parts) >= 4:
                    c_hash = parts[0]
                    author_name = parts[1]
                    author_email = parts[2].lower()
                    epoch_str = parts[3]
                    msg = parts[4] if len(parts) > 4 else ""
                    body = parts[5] if len(parts) > 5 else ""

                    try:
                        timestamp = datetime.utcfromtimestamp(int(epoch_str))
                    except (ValueError, TypeError):
                        timestamp = datetime.utcnow()

                    authors = [AuthorInfo(name=author_name, email=author_email)]
                    full_text = f"{msg}\n{body}"
                    for co_name, co_email in CO_AUTHOR_REGEX.findall(full_text):
                        co_name = co_name.strip()
                        co_email = co_email.strip().lower()
                        if not self._is_bot(co_name, co_email):
                            if not any(a.email == co_email for a in authors):
                                authors.append(AuthorInfo(name=co_name, email=co_email))

                    current_commit = CommitRecord(
                        hash=c_hash,
                        author_name=author_name,
                        author_email=author_email,
                        timestamp=timestamp,
                        message=msg,
                        authors=authors,
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

                    new_path, old_path = self._parse_rename_paths(raw_path)

                    if not self._is_ignored_file(new_path):
                        current_commit.changes.append(
                            FileChange(path=new_path, added=added, deleted=deleted, old_path=old_path)
                        )

        if current_commit and not self._is_bot(current_commit.author_name, current_commit.author_email):
            yield current_commit

        process.wait()
