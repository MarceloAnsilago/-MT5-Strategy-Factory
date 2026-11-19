"""Offline contracts; no terminal, compilation, broker or network access.

These checks do not execute MQL5. TestFinalReport.mq5 exercises the actual reducer
when separately compiled/run after authorization.
"""
from pathlib import Path
from decimal import Decimal
import hashlib
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / 'MQL5/Experts/MT5StrategyFactory/Estrategia_001'
OLD = (EA / 'MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak').read_text(encoding='utf-8-sig')
NEW = (EA / 'MT5SF_Estrategia_001.mq5').read_text(encoding='utf-8-sig')
HELPER = (EA / 'FinalReportTotals.mqh').read_text(encoding='utf-8')
SUITE = (EA / 'tests/TestFinalReport.mq5').read_text(encoding='utf-8')


def body(text, name):
    match = re.search(r'\b' + re.escape(name) + r'\([^;{}]*\)\s*\{', text)
    if not match:
        raise AssertionError(name)
    start = match.end()
    depth = 1
    quoted = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if not depth:
                return text[start:i]
    raise AssertionError('unclosed ' + name)


class ReportContracts(unittest.TestCase):
    def test_v122_preserved_byte_for_byte(self):
        raw = (EA / 'MT5SF_Estrategia_001.v1.22_pre_v1.23_001.mq5.bak').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'd98154e180c1e707469003fffd85357aa7ac10cfa510a4990da13a3ea7eae9af')

    def test_no_operational_changes_before_final_block(self):
        marker = '// -------- Final read-only accounting'
        before = OLD.split(marker)[0].replace('v1.22', 'v1.23').replace('version "1.22"', 'version "1.23"')
        self.assertEqual(before, NEW.split(marker)[0])

    def test_all_operational_callbacks_unchanged(self):
        for name in ['OnTick', 'OnTradeTransaction', 'OnTrade', 'OnTester']:
            with self.subTest(name=name):
                self.assertEqual(body(OLD, name), body(NEW, name))
        self.assertEqual(body(OLD, 'OnInit').replace('v1.22', 'v1.23'), body(NEW, 'OnInit'))
        self.assertEqual(body(OLD, 'OnDeinit').split('   PrintFormat(')[0],
                         body(NEW, 'OnDeinit').split('   FinalReportLine(')[0])

    def test_snapshot_and_attribution_functions_unchanged(self):
        for name in ['ReadFinalSnapshots', 'FinalMarketDeal', 'FinalDealLinkOwned',
                     'FinalOriginOwned', 'CallbackSawDeal', 'CallbackProcessedDeal', 'FinalDetailAllowed']:
            with self.subTest(name=name):
                self.assertEqual(body(OLD, name), body(NEW, name))

    def test_candidate_and_end_heuristic_unchanged(self):
        for start, end in [('bool own_origin=', '      if(!owned[i])')]:
            self.assertEqual(OLD.split(start)[1].split(end)[0], NEW.split(start)[1].split(end)[0])
        proof = body(NEW, 'FinalDealLinkOwned')
        self.assertIn('(ulong)deal.magic!=InpMagic', proof)
        self.assertIn('orders[found].magic!=InpMagic', proof)

    def test_reporting_has_no_mutation_or_callback_counter_writes(self):
        block = NEW.split('void ReconcileFinal(')[1].split('double OnTester(')[0]
        code = re.sub(r'//[^\n]*', '', block + HELPER)
        for name in ['OrderSend', 'OrderCheck', 'AuditExposure', 'LogDeal', 'QueueDeal',
                     'RecoverPosition', 'CancelOwnResiduals', 'PositionOpen', 'GlobalVariableSet']:
            self.assertNotRegex(code, r'\b' + name + r'\s*\(')
        self.assertNotRegex(code, r'\bg_(?:own_deals|exit_deals|sl_exits|tp_exits|halted|uncertain)\s*(?:\+\+|[+\-]?=(?!=))')

    def test_missing_history_and_statistics_never_print_default_zero(self):
        unavailable = body(NEW, 'FinalReportUnavailable')
        self.assertIn('records=UNAVAILABLE net=UNAVAILABLE', unavailable)
        self.assertIn('history_only=UNAVAILABLE', unavailable)
        self.assertIn('!g_final_tester_seen', body(NEW, 'FinalReadStatistic'))
        self.assertIn('GetLastError()==0 && MathIsValidNumber(value)', body(NEW, 'FinalReadStatistic'))
        self.assertIn('FinalReportAvailable(total,complete)', body(NEW, 'FinalReportGroup'))
        self.assertIn('complete && total.money_available', body(HELPER, 'FinalReportAvailable'))
        self.assertIn('return "UNAVAILABLE"', body(HELPER, 'FinalReportMoney'))
        self.assertIn('!readable', body(HELPER, 'FinalReportAdd'))

    def test_final_summary_and_detail_use_chunked_output(self):
        self.assertNotIn('PrintFormat(', body(NEW, 'ReconcileFinal'))
        self.assertNotIn('PrintFormat(', body(NEW, 'OnDeinit'))
        self.assertIn('StringSubstr(safe,index*180,180)', body(HELPER, 'FinalReportChunk'))
        for phase in ['OnTester', 'OnDeinit']:
            key = 'DEAL_' + str(2**64 - 1) + '_OBSERVATION'
            prefix = f'MT5SF001 FINAL phase={phase} section={key} part=100000/100000 '
            self.assertLess(len(prefix) + 180, 350)

    def test_separate_scopes_and_no_attribution_from_sum(self):
        report = body(NEW, 'ReconcileFinal')
        for label in ['CONFIRMED', 'INCONCLUSIVE', 'CALLBACKS', 'HISTORY_MARKET', 'RECONCILIATION']:
            self.assertIn('"' + label + '"', report)
        self.assertIn('attribution=NOT_ASSUMED', report)
        self.assertIn('global_minus_candidates', report)
        self.assertIn('readable_all_symbols', report)
        self.assertIn('snapshot_complete && confirmed_totals.money_available && inconclusive_totals.money_available', report)

    def test_historical_fixture_against_published_evidence(self):
        dossier = (ROOT / 'DOSSIE_BACKTEST_001_V122_20261118.md').read_text(encoding='utf-8')
        records = re.findall(r'FINAL_DEAL phase=OnTester ticket=(\d+) result=(\w+).*?profit=(-?[\d.]+)', dossier)
        self.assertEqual(len(records), 4)
        confirmed = sum((Decimal(profit) for _, state, profit in records if state == 'CONFIRMED'), Decimal(0))
        inconclusive = sum((Decimal(profit) for _, state, profit in records if state == 'INCONCLUSIVE'), Decimal(0))
        self.assertEqual((confirmed, inconclusive, confirmed + inconclusive), (Decimal(89), Decimal(-4), Decimal(85)))
        self.assertIn('ticket=5 result=INCONCLUSIVE symbol=PETR4 magic=0 position_id=4', dossier)
        self.assertIn('final balance 10085.00 BRL', dossier)

    def test_mql_isolated_suite_covers_partial_costs_overflow_and_repeated_pass(self):
        for label in ['failed field read', 'unavailability stays sticky', 'partial sum hidden',
                      'all cost fields', 'non-finite money', 'overflow unavailable',
                      'fresh final pass, no double count', 'history-only inconclusive',
                      'incomplete snapshot hides even confirmed total']:
            self.assertIn(label, SUITE)
        for name in ['OrderSend', 'OrderCheck', 'TesterStatistics', 'HistorySelect', 'iMA', 'OnTick']:
            self.assertNotRegex(SUITE, r'\b' + name + r'\s*\(')


if __name__ == '__main__':
    unittest.main(verbosity=2)
