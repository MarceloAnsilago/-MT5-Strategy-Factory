"""SYNTHETIC offline fixtures for actual generated MQL decision expressions.

No indicator calculation, compiler, Tester, account, network or trade request.
These cases establish logical satisfiability, not occurrence in market history.
"""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import unittest

from strategy_factory.generator import render, verify_candidate
from strategy_factory.analysis import read_artifact

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT/'MQL5/Experts/MT5StrategyFactory/Generated/g1_a7e690b3b483dde0'
SOURCE = (CANDIDATE/'MT5SF_G_a7e690b3b483dde0.mq5').read_text(encoding='utf-8')


def decision(name, buffers):
    """Evaluate only the comparisons/AND extracted verbatim from the EA."""
    matches = re.findall(r'bool '+re.escape(name)+r'=(.*);', SOURCE)
    if len(matches) != 1:
        raise ValueError('expected exactly one generated decision')
    tree = ast.parse(matches[0].replace('&&', ' and '), mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Compare, ast.Gt, ast.Lt,
               ast.GtE, ast.LtE, ast.Name, ast.Subscript, ast.Constant, ast.Load)
    if any(not isinstance(n, allowed) for n in ast.walk(tree)):
        raise ValueError('unsupported decision syntax')
    if any(n.id not in buffers for n in ast.walk(tree) if isinstance(n, ast.Name)):
        raise ValueError('unknown decision buffer')
    return eval(compile(tree, '<SYNTHETIC offline MQL predicate>', 'eval'),
                {'__builtins__': {}}, buffers)


def fixture(side):
    """Arbitrary buffer values, never represented as observed PETR4 prices."""
    if side == 'long':
        return dict(h1b0=[100,102], h2b0=[99,100], h0b0=[24,25],
                    h0b1=[20,30], h0b2=[30,20], close=[100,103], h3b0=[50,56])
    return dict(h1b0=[100,98], h2b0=[101,100], h0b0=[24,25],
                h0b1=[30,20], h0b2=[20,30], close=[100,97], h3b0=[50,44])


class TrendPreflightTests(unittest.TestCase):
    def test_source_spec_identity_is_deterministic_without_file_mutation(self):
        paths = [p for p in CANDIDATE.iterdir() if p.is_file()]
        before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        metadata = verify_candidate(CANDIDATE)
        spec = read_artifact(CANDIDATE/'spec.json')
        self.assertEqual(render(spec)[2], metadata)
        self.assertEqual(before, {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_long_entry_is_satisfiable(self):
        b = fixture('long')
        self.assertTrue(decision('enter_long', b))
        self.assertFalse(decision('enter_short', b))

    def test_short_entry_is_satisfiable_and_distinct_from_long_exit(self):
        b = fixture('short')
        self.assertTrue(decision('enter_short', b))
        self.assertFalse(decision('enter_long', b))
        # Price below EMA alone closes a long but cannot establish a short signal.
        b['h3b0'][1] = 50
        self.assertTrue(decision('exit_long', b))
        self.assertFalse(decision('enter_short', b))

    def test_each_entry_filter_independently_blocks_each_side(self):
        for side in ('long', 'short'):
            original = fixture(side)
            changes = [('h1b0',1,100), ('h2b0',0,100), ('h0b0',1,24.99),
                       ('h0b1',1,original['h0b2'][1]),
                       ('close',1,original['h1b0'][1]),
                       ('h3b0',1,55 if side == 'long' else 45)]
            for key,index,value in changes:
                with self.subTest(side=side,filter=key,index=index):
                    b = deepcopy(original)
                    b[key][index] = value
                    self.assertFalse(decision('enter_'+side, b))

    def test_adx_threshold_is_inclusive_but_rsi_thresholds_are_strict(self):
        for side,level,inside in [('long',55,55.001),('short',45,44.999)]:
            b = fixture(side)
            self.assertTrue(decision('enter_'+side, b))  # ADX exactly 25.
            b['h3b0'][1] = level
            self.assertFalse(decision('enter_'+side, b))
            b['h3b0'][1] = inside
            self.assertTrue(decision('enter_'+side, b))

    def test_exit_directions_and_equality(self):
        b = fixture('long')
        b['close'][1] = b['h1b0'][1]
        self.assertFalse(decision('exit_long', b))
        self.assertFalse(decision('exit_short', b))
        b['close'][1] -= .01
        self.assertTrue(decision('exit_long', b))
        self.assertFalse(decision('exit_short', b))
        b['close'][1] += .02
        self.assertFalse(decision('exit_long', b))
        self.assertTrue(decision('exit_short', b))

    def test_synthetic_boundary_grid_never_opens_both_directions(self):
        observed = set()
        for ema20 in (99,100,101):
            for slope_previous in (99,100,101):
                for plus in (19,20,21):
                    for rsi in (44,45,50,55,56):
                        for price in (97,100,103):
                            b = fixture('long')
                            b['h1b0'][1] = ema20
                            b['h2b0'][0] = slope_previous
                            b['h0b1'][1] = plus
                            b['h3b0'][1] = rsi
                            b['close'][1] = price
                            long = decision('enter_long', b)
                            short = decision('enter_short', b)
                            self.assertFalse(long and short)
                            observed.add((long, short))
        self.assertEqual(observed, {(False,False),(True,False),(False,True)})


if __name__ == '__main__':
    unittest.main()
