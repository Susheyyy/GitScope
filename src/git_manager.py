from __future__ import annotations

import hashlib
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Set
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
        url_hash = hashlib.sha256(self.target.encode("utf-8")).hexdigest()[:12]
        repo_name = Path(urlparse(self.target).path).stem.replace(".git", "")
        dest = self.cache_dir / f"{repo_name}_{url_hash}"

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

        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"Invalid hostname in repository URL: {url}")

        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for addr in addr_info:
                ip_str = addr[4][0]
                ip = ipaddress.ip_address(ip_str)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                ):
                    raise ValueError(f"Access to private or internal network address is forbidden: {ip_str}")
        except socket.gaierror as e:
            raise ValueError(f"Unable to resolve host {hostname}: {e}")

    def get_existing_files(self) -> Set[str]:
        if not self.repo_path:
            raise RuntimeError("Repository has not been prepared.")
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
