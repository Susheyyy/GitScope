import unittest
from datetime import datetime
from gitscope.analyzer import AnalysisEngine
from gitscope.exporter import Exporter
from gitscope.parser import CommitRecord, FileChange


class TestAnalysis(unittest.TestCase):
    def test_hotspot_and_bus_factor_calculation(self):
        commits = [
            CommitRecord(
                hash="1111",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=datetime.utcnow(),
                message="Feature A",
                changes=[
                    FileChange(path="src/core.py", added=100, deleted=20),
                    FileChange(path="src/utils.py", added=10, deleted=2),
                ],
            ),
            CommitRecord(
                hash="2222",
                author_name="Alice",
                author_email="alice@example.com",
                timestamp=datetime.utcnow(),
                message="Fix A",
                changes=[
                    FileChange(path="src/core.py", added=50, deleted=10),
                ],
            ),
            CommitRecord(
                hash="3333",
                author_name="Bob",
                author_email="bob@example.com",
                timestamp=datetime.utcnow(),
                message="Feature B",
                changes=[
                    FileChange(path="src/utils.py", added=30, deleted=5),
                ],
            ),
        ]

        engine = AnalysisEngine(repo_name="test-repo", repo_path="/tmp/test-repo")
        report = engine.analyze(commits)

        self.assertEqual(report.total_commits, 3)
        self.assertEqual(report.total_authors, 2)

        core_item = next(item for item in report.hotspots_files if item.path == "src/core.py")
        self.assertEqual(core_item.commits, 2)
        self.assertEqual(core_item.total_churn, 180)
        self.assertEqual(core_item.bus_factor, 1)
        self.assertEqual(core_item.top_contributors[0].name, "Alice")
        self.assertEqual(core_item.top_contributors[0].ownership_percentage, 1.0)

        md_output = Exporter.to_markdown(report)
        self.assertIn("# 🔍 GitScope Report: `test-repo`", md_output)
        self.assertIn("src/core.py", md_output)

        json_output = Exporter.to_json(report)
        self.assertIn('"repo_name": "test-repo"', json_output)


if __name__ == "__main__":
    unittest.main()
