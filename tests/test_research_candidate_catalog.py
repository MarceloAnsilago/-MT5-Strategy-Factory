from copy import deepcopy
import json
from pathlib import Path
import unittest

from strategy_factory.generator import render
from strategy_factory.research.candidate_catalog import build_catalog, expand_grid


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = [
    ("g1_ff2190c4549a31aa", "4741ade1f856db724c591de8817fdc4ebb739a159f554658f4d11be52a8d0b8f"),
    ("g1_fcb7f99b53c86641", "d1ccbba691a8346951e1df676ef30ca7d7cc93fdcc9133f0d8acc597408a29c0"),
    ("g1_a7e690b3b483dde0", "2341c37562b7887a49309d29018827ece9bc00efa46bb730fcc6af02735d1805"),
]


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class CandidateCatalogTest(unittest.TestCase):
    def setUp(self):
        self.demos = read_json("config/generator/demo_specs.json")

    def test_golden_source_metadata_and_deduplication(self):
        reordered = dict(reversed(list(deepcopy(self.demos[2]).items())))
        reordered["entries"]["long"].reverse()
        reordered["entries"]["long"] = [
            dict(reversed(list(rule.items()))) for rule in reordered["entries"]["long"]
        ]
        self.assertEqual(render(reordered)[1], render(self.demos[2])[1])
        records = build_catalog(iter([*self.demos, reordered]), limit=3)
        self.assertEqual(
            [(record["candidate_id"], record["source_sha256"]) for record in records],
            GOLDEN,
        )
        for spec, record in zip(self.demos, records):
            _, source, metadata = render(spec)
            self.assertEqual(record, dict(metadata, status="source_only"))
            self.assertIsNone(record["compiled_sha256"])
            self.assertTrue(record["source_file"].endswith(".mq5"))
            self.assertIn("SYMBOL_VOLUME_MIN", source)
            self.assertIn("MQLInfoInteger(MQL_TESTER)", source)

    def test_example_grid(self):
        example = read_json("config/research/candidate_grid.example.json")
        base, axes = example["base"], example["axes"]
        snapshot = deepcopy(example)
        specs = expand_grid(base, axes)
        self.assertEqual(specs, expand_grid(base, dict(reversed(list(axes.items())))))
        self.assertEqual(example, snapshot)
        self.assertEqual(len(build_catalog(specs)), 8)
        self.assertEqual(render(specs[0])[2]["candidate_id"], GOLDEN[2][0])
        for spec in specs:
            self.assertEqual(spec["risk"], base["risk"])
            rules = {rule["kind"] for rule in spec["entries"]["long"]}
            self.assertTrue({"ma_trend", "rsi_level", "adx_direction"} <= rules)

    def test_limits_and_equivalent_choices(self):
        for limit in (0, 33, True, 1.0):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    expand_grid(self.demos[0], {}, limit=limit)
                with self.assertRaises(ValueError):
                    build_catalog(self.demos, limit=limit)
        with self.assertRaisesRegex(ValueError, "catalog exceeds"):
            build_catalog(self.demos, limit=2)
        with self.assertRaisesRegex(ValueError, "grid exceeds"):
            expand_grid(self.demos[0], {"risk.max_entries": list(range(1, 34))})
        specs = expand_grid(self.demos[0], {"risk.max_entries": list(range(1, 33))})
        self.assertEqual(len(build_catalog(specs)), 32)
        rules = self.demos[0]["entries"]["long"]
        self.assertEqual(
            expand_grid(self.demos[0], {"entries.long": [rules, rules[::-1], rules]}),
            expand_grid(self.demos[0], {}),
        )

    def test_rejects_invalid_axes_and_candidates(self):
        base = self.demos[0]
        rules = base["entries"]["long"]
        for axes, message in (
            ({"entries.long.5": [rules[0]]}, "existing field"),
            ({"entries.long": [rules], "entries.long.0.fast": [10]}, "overlapping"),
            ({"risk.max_entries": []}, "nonempty"),
            ({"risk.volume_mode": ["custom"]}, "minimum fixed"),
            ({"entries.long": [rules * 3]}, "five rules"),
            ({"risk.sl_percent": [21]}, "outside limits"),
        ):
            with self.subTest(axes=axes), self.assertRaisesRegex(ValueError, message):
                expand_grid(base, axes)

        pairs = [dict(rules[0], fast=2 + 2 * index, slow=3 + 2 * index) for index in range(9)]
        with self.assertRaisesRegex(ValueError, "handle limit"):
            expand_grid(base, {"entries.long": [pairs[:5]], "entries.short": [pairs[5:]]})
