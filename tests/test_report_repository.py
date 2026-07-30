from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repository.report_repository import ReportRepository


class ReportRepositoryTest(unittest.TestCase):
    def test_saves_markdown_report(self) -> None:
        with TemporaryDirectory() as directory:
            repository = ReportRepository(Path(directory))
            path = repository.save("selection_20260727.md", "# Report\n")

            content = path.read_text(encoding="utf-8")

        self.assertEqual(path.name, "selection_20260727.md")
        self.assertEqual(content, "# Report\n")

    def test_rejects_non_filename_or_non_markdown_name(self) -> None:
        with TemporaryDirectory() as directory:
            repository = ReportRepository(Path(directory))

            with self.assertRaisesRegex(ValueError, "simple .md filename"):
                repository.save("../report.md", "# Report\n")
            with self.assertRaisesRegex(ValueError, "simple .md filename"):
                repository.save("report.txt", "# Report\n")


if __name__ == "__main__":
    unittest.main()
