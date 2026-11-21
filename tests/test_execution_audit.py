"""Synthetic, offline-only execution evidence. No MT5, files, account or network."""
from copy import deepcopy
import unittest

from strategy_factory.execution_audit import audit_execution, attach_execution_audit, digest
from strategy_factory.analysis import summarize_run


def fixture():
    source = {'run_id':'synthetic-audit', 'kind':'SYNTHETIC', 'rows':['order','deal','reason']}
    ref = {'source':'native', 'locator':'synthetic rows'}
    orders = [dict(id='1',symbol='SYN',side='buy',requested_volume=10,filled_volume=10,
                   requested_price=100,state='filled',evidence=ref),
              dict(id='2',symbol='SYN',side='sell',requested_volume=10,filled_volume=10,
                   requested_price=99,state='filled',evidence=ref)]
    deals = [dict(id='d1',order_id='1',symbol='SYN',side='buy',entry='in',volume=10,
                  price=100,profit=0,commission=0,swap=0,fees=0,evidence=ref),
             dict(id='d2',order_id='2',symbol='SYN',side='sell',entry='out',volume=10,
                  price=98.5,profit=-15,commission=0,swap=0,fees=0,evidence=ref)]
    return dict(schema_version='1.0',run_id='synthetic-audit',
        sources={'native':{'payload':source,'sha256':digest(source)}},orders=orders,deals=deals,
        groups=[dict(id='g1',direction='long',entry_deals=['d1'],exit_deals=['d2'],
                     pairing_provenance='synthetic explicit links',evidence=ref)],
        exit_events=[dict(deal_id='d2',reason='stop_loss',evidence=ref)],counts_complete=True,
        costs_complete=True,contract_size=1,reported_net_profit=-15,
        identity={'disk_sha256':'a'*64,'runtime_sha256':'a'*64,'runtime_evidence':ref,
                  'disk_bytes':100,'journal_loaded_bytes':100})


class ExecutionAuditTests(unittest.TestCase):
    def audit(self, evidence):
        return audit_execution(evidence, expected_run_id='synthetic-audit')

    def test_stop_difference_is_signed_calculation_without_cause_inference(self):
        a=self.audit(fixture());o=a['orders'][1]
        self.assertEqual(o['adverse_price_difference'],.5)
        self.assertEqual(o['price_difference_pnl'],-5)
        self.assertEqual(a['trades'][0]['exit_reason'],'stop_loss')
        self.assertNotIn('gap',str(a));self.assertNotIn('slippage_cause',str(a))

    def test_sell_open_short_and_buy_close_are_distinguished_by_entry(self):
        e=fixture();e['groups'][0]['direction']='short'
        for rows in (e['orders'],e['deals']):
            rows[0]['side']='sell';rows[1]['side']='buy'
        a=self.audit(e)
        self.assertFalse(a['issues']);self.assertEqual(a['trades'][0]['direction'],'short')
        self.assertEqual(a['orders'][1]['adverse_price_difference'],-.5)

    def test_wrong_direction_or_order_symbol_is_inconsistent(self):
        for key,value in [('side','buy'),('symbol','OTHER')]:
            e=fixture();e['deals'][1][key]=value
            self.assertEqual(self.audit(e)['status'],'inconsistent')

    def test_exit_is_never_inferred_from_profit_price_or_comment(self):
        e=fixture();e['exit_events']=[];e['deals'][1].update(profit=20,comment='end of test')
        a=self.audit(e);self.assertEqual(a['trades'][0]['exit_reason'],'unknown')
        self.assertEqual(a['period_end_diagnostic']['count'],0)

    def test_all_explicit_exit_categories(self):
        for reason in ('strategy_signal','stop_loss','take_profit','period_end','other','unknown'):
            with self.subTest(reason=reason):
                e=fixture();e['exit_events'][0]['reason']=reason
                self.assertEqual(self.audit(e)['trades'][0]['exit_reason'],reason)

    def test_period_end_is_separate_without_replacing_pnl(self):
        e=fixture();e['exit_events'][0]['reason']='period_end'
        a=self.audit(e);self.assertEqual(a['period_end_diagnostic']['profit_recorded'],-15)
        self.assertEqual(a['recorded_totals']['profit'],-15)
        self.assertEqual(a['period_end_diagnostic']['count'],1)

    def test_conflicting_reasons_are_not_resolved_by_precedence(self):
        e=fixture();e['exit_events'].append(dict(e['exit_events'][0],reason='period_end'))
        self.assertEqual(self.audit(e)['trades'][0]['exit_reason'],'unknown')

    def test_event_for_unknown_or_entry_deal_is_inconsistent(self):
        for deal_id in ('missing','d1'):
            e=fixture();e['exit_events'][0]['deal_id']=deal_id
            self.assertIn('exit_event_has_no_exit_deal',self.audit(e)['issues'])

    def test_partial_execution_and_volume_mismatch_detected(self):
        e=fixture();e['orders'][0]['filled_volume']=4
        a=self.audit(e)
        self.assertTrue(a['orders'][0]['partial_execution'])
        self.assertIn('order_deal_volume_mismatch:1',a['issues'])

    def test_multiple_fills_use_volume_weighted_price(self):
        e=fixture();e['deals'][1]['volume']=4
        e['deals'].append(dict(e['deals'][1],id='d3',volume=6,price=99.5,profit=0))
        e['groups'][0]['exit_deals'].append('d3')
        e['exit_events'].append(dict(e['exit_events'][0],deal_id='d3'))
        a=self.audit(e)
        self.assertEqual(a['orders'][1]['executed_vwap'],99.1)
        self.assertFalse(a['issues'])

    def test_unknown_cause_on_one_partial_exit_does_not_classify_whole_trade(self):
        e=fixture();e['deals'][1]['volume']=4
        e['deals'].append(dict(e['deals'][1],id='d3',volume=6))
        e['groups'][0]['exit_deals'].append('d3')
        e['exit_events'].append(dict(e['exit_events'][0],deal_id='d3',reason='unknown'))
        self.assertEqual(self.audit(e)['trades'][0]['exit_reason'],'unknown')

    def test_missing_cost_is_not_zero_and_net_is_unavailable(self):
        for key in ('commission','swap','fees'):
            e=fixture();e['deals'][0][key]=None
            a=self.audit(e);self.assertIsNone(a['recorded_totals'][key])
            self.assertIsNone(a['net_after_all_costs']);self.assertFalse(a['costs_complete'])

    def test_explicit_zero_costs_and_finite_net_reconciliation(self):
        a=self.audit(fixture());self.assertEqual(a['net_after_all_costs'],-15)
        self.assertTrue(a['costs_complete'])
        e=fixture();e['reported_net_profit']=12
        self.assertIn('deal_net_profit_mismatch',self.audit(e)['issues'])

    def test_incomplete_collection_does_not_claim_totals(self):
        e=fixture();e['counts_complete']=False
        a=self.audit(e);self.assertIsNone(a['recorded_totals']['profit'])
        self.assertIsNone(a['net_after_all_costs'])

    def test_unavailable_deals_are_not_an_empty_complete_history(self):
        e=fixture();e.update(deals=None,exit_events=[])
        a=self.audit(e)
        self.assertFalse(a['issues']);self.assertEqual(a['trades'],[])
        self.assertIn('deals_unavailable',a['warnings'])
        self.assertIsNone(a['orders'][0]['deal_volume'])

    def test_missing_profit_keeps_net_unknown_even_with_known_costs(self):
        e=fixture();e['deals'][0]['profit']=None
        a=self.audit(e)
        self.assertIsNone(a['net_after_all_costs'])
        self.assertIn('recorded_profit_unavailable',a['warnings'])

    def test_unknown_order_volume_stays_unknown(self):
        e=fixture();e['orders'][0]['requested_volume']=None
        a=self.audit(e)
        self.assertIsNone(a['orders'][0]['partial_execution'])
        self.assertIn('order_volume_unverifiable:1',a['warnings'])

    def test_size_difference_alone_never_proves_binary_difference(self):
        e=fixture();e['identity']={'disk_sha256':'a'*64,'disk_bytes':100,'journal_loaded_bytes':189}
        a=self.audit(e)
        self.assertEqual(a['binary_identity']['status'],'unverified')
        self.assertEqual(a['binary_identity']['loaded_minus_disk_bytes'],89)
        self.assertFalse(a['binary_identity']['size_difference_proves_different_binary'])
        self.assertFalse(a['issues'])

    def test_equal_sizes_or_hash_declarations_without_runtime_evidence_are_unverified(self):
        e=fixture();del e['identity']['runtime_evidence']
        self.assertEqual(self.audit(e)['binary_identity']['status'],'unverified')

    def test_observed_runtime_hash_mismatch_is_inconsistent(self):
        e=fixture();e['identity']['runtime_sha256']='b'*64
        self.assertIn('runtime_binary_hash_mismatch',self.audit(e)['issues'])

    def test_duplicate_ids_missing_refs_and_mutated_source_rejected(self):
        e=fixture();e['orders'].append(deepcopy(e['orders'][0]))
        with self.assertRaises(ValueError):self.audit(e)
        e=fixture();e['deals'][0]['evidence']['source']='missing'
        with self.assertRaises(ValueError):self.audit(e)
        e=fixture();e['sources']['native']['payload']['rows'].append('tampered')
        with self.assertRaises(ValueError):self.audit(e)

    def test_wrong_run_and_native_scope_rejected(self):
        e=fixture();e['run_id']='other'
        with self.assertRaises(ValueError):self.audit(e)
        e=fixture();p=e['sources']['native']['payload'];p['run_id']='other'
        e['sources']['native']['sha256']=digest(p)
        with self.assertRaises(ValueError):self.audit(e)

    def test_invalid_numbers_and_missing_data(self):
        for value in (True,'NaN','Infinity','1e308',-1):
            e=fixture();e['deals'][0]['volume']=value
            with self.assertRaises(ValueError):self.audit(e)
        e=fixture();e.update(orders=None,deals=None,groups=None,exit_events=[])
        a=self.audit(e);self.assertIsNone(a['net_after_all_costs'])
        self.assertEqual(a['orders'],[])

    def test_bad_prices_byte_counts_and_source_refs_rejected(self):
        for value in (0,-1,True):
            e=fixture();e['deals'][0]['price']=value
            with self.assertRaises(ValueError):self.audit(e)
        for value in (-1,1.5,True):
            e=fixture();e['identity']['disk_bytes']=value
            with self.assertRaises(ValueError):self.audit(e)
        e=fixture();e['deals'][0]['evidence']=None
        with self.assertRaises(ValueError):self.audit(e)

    def test_no_duplicate_deals_between_groups_or_unmatched_order(self):
        e=fixture();e['groups'].append(dict(e['groups'][0],id='g2'))
        self.assertIn('deal_reused_across_groups:g2',self.audit(e)['issues'])
        e=fixture();e['deals'][0]['order_id']='missing'
        self.assertIn('deal_has_no_matching_order:d1',self.audit(e)['issues'])

    def test_open_or_overclosed_position_flagged(self):
        e=fixture();e['groups'][0]['exit_deals']=[]
        self.assertFalse(self.audit(e)['trades'][0]['closed'])
        e=fixture();e['deals'][1]['volume']=11
        self.assertIn('exit_volume_exceeds_entry:g1',self.audit(e)['issues'])

    def test_sidecar_preserves_summary_and_all_historical_metrics(self):
        e=fixture();s=dict(schema_version='1.1',artifact_type='run_summary',run_id='synthetic-audit',
            warnings=[],metrics={'net_profit':{'value':-15}},data_quality={'classification':'complete'})
        original=deepcopy(s);before=deepcopy(e)
        a=attach_execution_audit(s,e)
        self.assertEqual(a['metrics'],s['metrics']);self.assertEqual(s,original);self.assertEqual(e,before)
        a['execution_audit']['issues'].append('mutated')
        self.assertFalse(self.audit(e)['issues'])

    def test_optional_summary_integration_is_backward_compatible(self):
        params=dict(expert=r'C:\SYNTHETIC\safe.ex5',symbol='SYN',timeframe='M5',from_date='2026-01-01',
            to_date='2026-01-02',deposit=1000,currency='BRL',leverage=1,model='every tick',execution_delay=0)
        kwargs=dict(parameters=params,run_id='synthetic-audit',inputs={},execution={'status':'completed'},synthetic=True)
        base=summarize_run(None,**kwargs)
        self.assertEqual(base,summarize_run(None,execution_evidence=None,**kwargs))
        enriched=summarize_run(None,execution_evidence=fixture(),**kwargs)
        self.assertEqual(base['metrics'],enriched['metrics'])
        self.assertEqual(enriched['schema_version'],'1.1')

    def test_inconsistent_sidecar_excludes_quality_without_erasing_metrics(self):
        e=fixture();e['deals'][0]['order_id']='missing'
        s=dict(schema_version='1.1',artifact_type='run_summary',run_id='synthetic-audit',
            warnings=[],metrics={'net_profit':{'value':-15}},data_quality={'classification':'complete'})
        a=attach_execution_audit(s,e)
        self.assertEqual(a['data_quality']['classification'],'invalid')
        self.assertEqual(a['metrics'],s['metrics'])


if __name__=='__main__':
    unittest.main()
