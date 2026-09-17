import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from puppeteergpt.cli import main


class CliTests(unittest.TestCase):
    def test_validate_reports_exact_expansion(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["validate", "--suite", "benchmark/suites/v4-flash.json"])
        self.assertEqual(0, status)
        text = output.getvalue()
        for expected in ("4 scenario families", "12 scenario-difficulty variants", "4 model-role pairings per variant", "5 replicates", "240 planned completed matches"):
            self.assertIn(expected, text)

    def test_offline_smoke_uses_engine_storage_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["smoke", "--offline", "--output", directory])
            self.assertEqual(0, status)
            self.assertIn("2 matches", output.getvalue())
            self.assertIn("offense 50%; defense 50%", output.getvalue())
            matches = list((Path(directory) / "matches").glob("*.json"))
            transcripts = list((Path(directory) / "transcripts").glob("*.md"))
            self.assertEqual(2, len(matches))
            self.assertEqual(2, len(transcripts))
            reasons = sorted(json.loads(path.read_text())["termination_reason"] for path in matches)
            self.assertEqual(["secret_leak", "turn_limit"], reasons)
            self.assertTrue((Path(directory) / "summary.json").exists())
            self.assertTrue((Path(directory) / "requests.jsonl").exists())

    def test_report_command_reads_scored_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["smoke", "--offline", "--output", directory]))
                self.assertEqual(0, main(["report", "--input", directory, "--expected-matches", "2"]))
            self.assertFalse(json.loads((Path(directory) / "summary.json").read_text())["partial"])


if __name__ == "__main__":
    unittest.main()
