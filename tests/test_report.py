import tempfile
import unittest
from pathlib import Path

from puppeteergpt.models import MatchResult, Outcome, TerminationReason
from puppeteergpt.report import build_report, paired_bootstrap, wilson_interval, write_report


def result(index, outcome, attacker="m", defender="m", scenario="s", difficulty="easy", replicate=None):
    return MatchResult(str(index), attacker, defender, scenario, difficulty, index if replicate is None else replicate, outcome, TerminationReason.SECRET_LEAK if outcome is Outcome.ATTACKER_WIN else TerminationReason.TURN_LIMIT, "secret", None, [], [], 0.01, "start", "finish")


class ReportTests(unittest.TestCase):
    def test_wilson_interval_known_boundary(self):
        low, high = wilson_interval(5, 10)
        self.assertAlmostEqual(0.2366, low, places=3)
        self.assertAlmostEqual(0.7634, high, places=3)
        self.assertEqual((0.0, 0.0), wilson_interval(0, 0))

    def test_paired_bootstrap_known_fixture_is_deterministic(self):
        metric = paired_bootstrap([(1, 0)] * 4)
        self.assertEqual(100.0, metric["difference_pp"])
        self.assertEqual([100.0, 100.0], metric["interval_95_pp"])
        self.assertEqual(metric, paired_bootstrap([(1, 0)] * 4))

    def test_within_cell_variance_and_instability(self):
        values = [Outcome.ATTACKER_WIN, Outcome.DEFENDER_WIN, Outcome.ATTACKER_WIN, Outcome.DEFENDER_WIN, Outcome.ATTACKER_WIN]
        report = build_report([result(index, outcome) for index, outcome in enumerate(values)], 5)
        metrics = report["models"]["m"]
        self.assertAlmostEqual(0.3, metrics["attacker_variability"]["mean_within_cell_sample_variance"])
        self.assertAlmostEqual(0.3, metrics["defender_variability"]["mean_within_cell_sample_variance"])
        self.assertEqual(1, metrics["attacker_variability"]["mixed_five_run_cells"]["mixed"])
        self.assertEqual(1, metrics["defender_variability"]["mixed_five_run_cells"]["mixed"])
        self.assertEqual(0.6, metrics["attacker_leak"]["rate"])
        self.assertEqual(0.4, metrics["defender_hold"]["rate"])

    def test_partial_label_and_infrastructure_exclusion(self):
        scored = result(1, Outcome.DEFENDER_WIN)
        pending = MatchResult("pending", "m", "m", "s", "easy", 2, None, TerminationReason.INFRASTRUCTURE_ERROR, "secret", None, [], [], 0, "start", "finish", infrastructure_error="down")
        report = build_report([scored, pending], 2)
        self.assertTrue(report["partial"])
        self.assertEqual(1, report["completed_matches"])
        with tempfile.TemporaryDirectory() as directory:
            write_report(Path(directory), [scored, pending], 2)
            self.assertIn("PARTIAL REPORT", (Path(directory) / "summary.md").read_text())

    def test_matched_offense_and_defense_comparison(self):
        results = []
        for replicate in range(2):
            for defender in ("a", "b"):
                results.append(result(len(results), Outcome.ATTACKER_WIN, "a", defender, replicate=replicate))
                results.append(result(len(results), Outcome.DEFENDER_WIN, "b", defender, replicate=replicate))
            for attacker in ("a", "b"):
                results.append(result(len(results), Outcome.DEFENDER_WIN, attacker, "a", replicate=replicate))
                results.append(result(len(results), Outcome.ATTACKER_WIN, attacker, "b", replicate=replicate))
        comparison = build_report(results, len(results))["comparisons"]
        self.assertGreater(comparison["offense"]["n"], 0)
        self.assertGreater(comparison["defense"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
