import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from puppeteergpt.models import MatchResult, Message, Outcome, Role, TerminationReason
from puppeteergpt.storage import RequestLedger, ResultStore


class StorageTests(unittest.TestCase):
    def result(self, match_id="abc"):
        return MatchResult(match_id, "a", "d", "s", "easy", 0, Outcome.ATTACKER_WIN, TerminationReason.SECRET_LEAK, "secret", None, [Message(Role.TARGET, "secret", 1, 1)], [], 0.0, "start", "finish", verifier_message_index=0)

    def test_atomic_result_and_transcript_support_resume_skipping(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResultStore(Path(directory))
            self.assertFalse(store.has_scored("abc"))
            store.save(self.result())
            self.assertTrue(store.has_scored("abc"))
            self.assertEqual(1, len(store.load_all()))
            transcript = (Path(directory) / "transcripts" / "abc.md").read_text()
            self.assertIn("VERIFIED SECRET LEAK", transcript)
            self.assertFalse(any(path.name.startswith(".abc") for path in (Path(directory) / "matches").iterdir()))

    def test_unscored_infrastructure_result_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.result()
            result = MatchResult(**{**result.__dict__, "outcome": None, "termination_reason": TerminationReason.INFRASTRUCTURE_ERROR})
            with self.assertRaises(ValueError):
                ResultStore(Path(directory)).save(result)

    def test_ledger_restores_utc_daily_charges_and_stops_at_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            day = datetime.now(UTC).date().isoformat()
            (path / "requests.jsonl").write_text(json.dumps({"timestamp": day + "T00:00:00+00:00", "cost": 0.4}) + "\n")
            ledger = RequestLedger(path, 0.4)
            self.assertAlmostEqual(0.4, ledger.spent_today())
            self.assertFalse(ledger.budget_available())

    def test_append_is_immediately_visible_and_accumulated(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RequestLedger(Path(directory), 1)
            ledger.append({"cost": 0.1, "status": "charged"})
            ledger.append({"cost": 0.2, "status": "charged"})
            self.assertAlmostEqual(0.3, ledger.spent_today())
            self.assertEqual(2, len(ledger.path.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
