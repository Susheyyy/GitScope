import unittest
from datetime import datetime, timezone
from analyzer import AnalysisEngine
from exporter import Exporter
from git_manager import GitRepoManager
from parser import AuthorInfo, CommitRecord, FileChange, GitLogParser


class TestGitScope(unittest.TestCase):
    def test_hotspot_and_bus_factor_calculation(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="1111",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="feat: Feature A",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[
                    FileChange(path="src/core.py", added=100, deleted=20),
                    FileChange(path="src/utils.py", added=10, deleted=2),
                ],
            ),
            CommitRecord(
                hash="2222",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="fix(core): Fix A",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[
                    FileChange(path="src/core.py", added=50, deleted=10),
                ],
            ),
            CommitRecord(
                hash="3333",
                author_name="Bob",
                author_email="bob@example.com",
                timestamp=now,
                message="feat: Feature B",
                authors=[AuthorInfo(name="Bob", email="bob@example.com")],
                changes=[
                    FileChange(path="src/utils.py", added=30, deleted=5),
                ],
            ),
        ]

        engine = AnalysisEngine(
            repo_name="test-repo",
            repo_path="/tmp/test-repo",
            existing_files={"src/core.py", "src/utils.py"},
        )
        report = engine.analyze(commits)

        self.assertEqual(report.total_commits, 3)
        self.assertEqual(report.total_authors, 2)

        core_item = next(item for item in report.hotspots_files if item.path == "src/core.py")
        self.assertEqual(core_item.commits, 2)
        self.assertEqual(core_item.total_churn, 180)
        self.assertEqual(core_item.bus_factor, 1)
        self.assertFalse(core_item.is_deleted)
        self.assertEqual(core_item.top_contributors[0].name, "Alice")

    def test_conventional_commits_and_vague_messages(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="c1",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="fix: harden architectural flaws",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[FileChange(path="src/a.py", added=10, deleted=2)],
            ),
            CommitRecord(
                hash="c2",
                author_name="Bob",
                author_email="bob@example.com",
                timestamp=now,
                message="ui fixes",
                authors=[AuthorInfo(name="Bob", email="bob@example.com")],
                changes=[FileChange(path="src/b.py", added=20, deleted=5)],
            ),
        ]
        engine = AnalysisEngine(repo_name="test-repo", repo_path="/tmp/test-repo")
        report = engine.analyze(commits)

        self.assertEqual(report.hygiene.conventional_count, 1)
        self.assertEqual(report.hygiene.vague_commits_count, 1)

        alice_prof = next(c for c in report.contributors if c.name == "Alice")
        bob_prof = next(c for c in report.contributors if c.name == "Bob")

        self.assertEqual(alice_prof.hygiene.hygiene_score, 100)
        self.assertLess(bob_prof.hygiene.hygiene_score, 100)

        badge_svg = Exporter.to_badge_svg("gitscope score", "85/100")
        self.assertIn("<svg", badge_svg)
        self.assertIn("85/100", badge_svg)

    def test_rename_tracking(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="aaaa",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="feat: Create old.py",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[FileChange(path="src/old.py", added=50, deleted=0)],
            ),
            CommitRecord(
                hash="bbbb",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="refactor: Rename old.py to new.py",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[FileChange(path="src/new.py", added=20, deleted=5, old_path="src/old.py")],
            ),
        ]
        engine = AnalysisEngine(repo_name="test-repo", repo_path="/tmp/test-repo")
        report = engine.analyze(commits)

        file_paths = [f.path for f in report.hotspots_files]
        self.assertIn("src/new.py", file_paths)
        new_item = next(f for f in report.hotspots_files if f.path == "src/new.py")
        self.assertEqual(new_item.commits, 2)
        self.assertEqual(new_item.total_churn, 75)

    def test_temporal_coupling(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="c1",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="feat: Mod 1",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[
                    FileChange(path="src/service.py", added=10, deleted=0),
                    FileChange(path="src/routes.py", added=10, deleted=0),
                ],
            ),
            CommitRecord(
                hash="c2",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="feat: Mod 2",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[
                    FileChange(path="src/service.py", added=5, deleted=2),
                    FileChange(path="src/routes.py", added=5, deleted=2),
                ],
            ),
        ]
        engine = AnalysisEngine(repo_name="test-repo", repo_path="/tmp/test-repo")
        report = engine.analyze(commits)

        self.assertTrue(len(report.coupled_files) > 0)
        pair = report.coupled_files[0]
        self.assertEqual(pair.together_commits, 2)
        self.assertEqual(pair.coupling_percentage, 100.0)

    def test_co_author_split(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="cccc",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="feat: Pair commit",
                authors=[
                    AuthorInfo(name="Alice", email="alice@example.com"),
                    AuthorInfo(name="Bob", email="bob@example.com"),
                ],
                changes=[FileChange(path="src/pair.py", added=100, deleted=0)],
            )
        ]
        engine = AnalysisEngine(repo_name="test-repo", repo_path="/tmp/test-repo")
        report = engine.analyze(commits)

        item = next(f for f in report.hotspots_files if f.path == "src/pair.py")
        self.assertEqual(len(item.top_contributors), 2)
        self.assertEqual(item.top_contributors[0].ownership_percentage, 0.5)
        self.assertEqual(item.top_contributors[1].ownership_percentage, 0.5)

    def test_deleted_file_flag(self):
        now = datetime.now(timezone.utc)
        commits = [
            CommitRecord(
                hash="dddd",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=now,
                message="chore: Removed file",
                authors=[AuthorInfo(name="Alice", email="alice@example.com")],
                changes=[FileChange(path="src/dead.py", added=10, deleted=50)],
            )
        ]
        engine = AnalysisEngine(
            repo_name="test-repo",
            repo_path="/tmp/test-repo",
            existing_files={"src/alive.py"},
        )
        report = engine.analyze(commits)
        item = next(f for f in report.hotspots_files if f.path == "src/dead.py")
        self.assertTrue(item.is_deleted)

    def test_ssrf_validation(self):
        with self.assertRaises(ValueError):
            GitRepoManager._validate_remote_url("http://127.0.0.1/evil.git")
        with self.assertRaises(ValueError):
            GitRepoManager._validate_remote_url("http://localhost:8080/evil.git")


if __name__ == "__main__":
    unittest.main()
