"""Synthetic ATR reference checks and static indicator source checks."""

from pathlib import Path
import unittest

from strategy_factory.research.indicator_reference import atr


class AtrTests(unittest.TestCase):
    def test_reference_vector(self):
        self.assertEqual(atr([11, 13, 14], [9, 10, 11], [10, 12, 13], 2),
                         [None, 2.5, 2.75])

    def test_gaps_and_prefix(self):
        high = [11, 16, 7, 10]
        low = [9, 14, 5, 8]
        close = [10, 15, 6, 9]
        # TRs are 2, 6, 10, 4. Seed 4, then (4+10)/2 and (7+4)/2.
        expected = [None, 4.0, 7.0, 5.5]
        for end in range(len(high) + 1):
            with self.subTest(end=end):
                self.assertEqual(atr(high[:end], low[:end], close[:end], 2),
                                 expected[:end])
        self.assertEqual(atr(high, low, close, 1), [2.0, 6.0, 10.0, 4.0])
        self.assertEqual(atr(high, low, close, 5), [None] * 4)

    def test_invalid_input(self):
        for period in (False, True, 0, -1, 2.0, "2", None):
            with self.subTest(period=period), self.assertRaises(ValueError):
                atr([], [], [], period)
        for prices in (([1], [], [1]), ([1], [2], [1]), ([None], [0], [1]),
                       ([1], [float("nan")], [1]), ([1], [0], [float("inf")])):
            with self.subTest(prices=prices), self.assertRaises(ValueError):
                atr(*prices, period=2)

    def test_indicator_source(self):
        path = Path(__file__).resolve().parents[1] / "src/mql5/Indicators/SF_ATR_Research.mq5"
        source = path.read_text(encoding="utf-8")
        self.assertIn("OnCalculate", source)
        self.assertIn("native_validation_pending", source)
        self.assertNotRegex(
            source, r"(?i)OrderSend|CTrade|WebRequest|#\s*import|\.dll|"
                    r"\b(?:Socket\w*|AccountInfo\w*)\s*\(",
        )
