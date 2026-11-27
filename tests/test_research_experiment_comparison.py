"""Independent scenarios using synthetic run summaries only."""

from pathlib import Path
import unittest

from strategy_factory.analysis import read_artifact
from strategy_factory.research.experiment_comparison import compare_experiments


FIXTURE = Path(__file__).parent / "fixtures/research/summaries_synthetic.json"


class ExperimentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.summaries = read_artifact(FIXTURE)

    def test_empty(self):
        result = compare_experiments([])
        self.assertEqual(result["ranked"], [])
        self.assertIs(result["live_execution_enabled"], False)

    def test_out_of_sample_ranking_and_stable_tie(self):
        result = compare_experiments(self.summaries)
        self.assertEqual(result, compare_experiments(reversed(self.summaries)))
        rows = result["ranked"]
        self.assertEqual([row["run_id"] for row in rows], ["synthetic-a", "synthetic-c", "synthetic-b"])
        self.assertEqual([row["out_of_sample"]["net_profit"] for row in rows], [40, 40, -20])
        self.assertTrue(all(row["out_of_sample"]["win_rate"] is None for row in rows))
        self.assertTrue(all(row["margin"] is None and not row["promotion_eligible"] for row in rows))
        self.assertTrue(all(row["evidence_kind"] == "synthetic" for row in rows))
        self.assertTrue(all(criterion["reason"] for criterion in result["criteria"]))

    def test_divergent_context(self):
        for group, field, value in (
            ("data_context", "history_fingerprint", "c" * 64),
            ("data_context", "costs_fingerprint", "d" * 64),
            ("parameters", "model", "open prices"),
            ("parameters", "from_date", "2024-02-01"),
        ):
            with self.subTest(field=field):
                first, second, *_ = read_artifact(FIXTURE)
                second[group][field] = value
                result = compare_experiments([first, second])
                self.assertEqual(result["ranked"], [])
                self.assertEqual(result["pairs"][0]["classification"], "not_comparable")

    def test_missing_context_costs_and_provenance(self):
        for group, field in (
            ("data_context", "costs_fingerprint"),
            ("readiness", "cost_configuration"),
            ("reconciliation", "classification"),
        ):
            with self.subTest(field=field):
                first = read_artifact(FIXTURE)[0]
                if group == "readiness":
                    first["traceability"][group][field] = False
                else:
                    first[group][field] = None if group == "data_context" else "partial"
                self.assertEqual(compare_experiments([first])["ranked"], [])

    def test_missing_out_of_sample_keeps_final_test_out(self):
        first = self.summaries[0]
        first["period_results"][1].pop("net_profit")
        self.assertEqual(compare_experiments([first])["ranked"], [])

    def test_simulated_failed_and_source_only_cannot_rank(self):
        for status in ("simulated", "failed", "unknown", "source_only"):
            with self.subTest(status=status):
                first = read_artifact(FIXTURE)[0]
                if status == "source_only":
                    first["status"] = status
                else:
                    first["execution"]["status"] = status
                if status == "simulated":
                    first["evidence_kind"] = "simulation"
                self.assertEqual(compare_experiments([first])["ranked"], [])

    def test_malformed_and_non_finite_raise(self):
        with self.assertRaises((ValueError, TypeError)):
            compare_experiments([{}])
        first = self.summaries[0]
        for value in (float("nan"), float("inf"), float("-inf"), "40"):
            with self.subTest(value=value):
                first["period_results"][-1]["net_profit"] = value
                with self.assertRaises((ValueError, TypeError)):
                    compare_experiments([first])
        first["period_results"][-1]["net_profit"] = 0
        del first["metrics"]["trades"]
        with self.assertRaises((ValueError, TypeError)):
            compare_experiments([first])
