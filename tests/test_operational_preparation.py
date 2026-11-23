"""Offline contract laboratory and readiness tests; no executable approvals."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.batch_safety import execution_gate,validate_plan
from strategy_factory.consent_contract import review_context,validate_consent_fixture,ConsentSimulationLedger
from strategy_factory.integration_policy import ResourcePolicy,AcceptanceCriteria
from strategy_factory.period_planning import inventory_local_history,propose_periods,validate_candidate_periods
from strategy_factory.operational_review import review_checklist,classify_metadata,assess_resource_proposal,SAFETY_KEYS,DECISIONS,INTEGRATION_EVIDENCE
from strategy_factory.readiness import FIELDS,assess_readiness
from strategy_factory.homologation_transport import HomologationTransport
from strategy_factory.tester_adapter import OperationalTesterAdapter

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,23,12,tzinfo=timezone.utc)


def consent_fixture(context,identity='synthetic-human-fixture'):
    """Test data only; not an issuer and not a real assertion of human consent."""
    checksum=fingerprint(context)
    return dict(schema_version='3.3D-contract-1',fixture_kind='synthetic_non_executable',scope='offline_contract_test',
        authorization_id=identity,context=deepcopy(context),context_sha256=checksum,issued_at=NOW.isoformat(),
        expires_at=(NOW+timedelta(minutes=5)).isoformat(),human_consent=dict(actor_kind='human_test_fixture',
        actor_id='synthetic-human-reviewer',context_sha256=checksum,
        statement='CONSENTIMENTO HUMANO SINTETICO PARA TESTE OFFLINE '+checksum))


class ConsentContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'laboratory'
        self.plan=read_artifact(ROOT/'config/batches/phase33a.synthetic.json')
        self.context=review_context(self.plan,'petr4-first',1,
            dict(installation_sha256='d'*64,server='Rico-DEMO',build=6230,environment='demo'),
            ResourcePolicy(),AcceptanceCriteria())
        self.record=consent_fixture(self.context)
        self.store=ConsentSimulationLedger(self.root)

    def register(self):self.store.register_fixture(self.record,self.context,now=NOW)
    def consume(self):return self.store.consume_fixture(self.record['authorization_id'],self.context,now=NOW)

    def test_complete_review_context_and_valid_fixture_are_non_executable(self):
        self.assertTrue(validate_consent_fixture(self.record,self.context,now=NOW))
        self.assertFalse(self.context['live_execution_enabled'])
        for key in ('manifest_sha256','controls_sha256','scenario_sha256','source_sha256','compiled_sha256','period','parameters','resources','terminal','attempt'):
            self.assertIn(key,self.context)
        self.register();receipt=self.consume()
        with patch.object(socket,'socket',side_effect=AssertionError('no network')):
            result=self.store.record_simulated_start(receipt,self.context,now=NOW)
        self.assertFalse(result['real_start_requested']);self.assertFalse(result['live_execution_enabled'])

    def test_absent_or_invalid_consent_and_agent_self_approval_rejected(self):
        with self.assertRaises(PermissionError):self.consume()
        for change in ('missing_record','missing_consent','agent','wrong_phrase'):
            r=deepcopy(self.record)
            if change=='missing_record':r=None
            if change=='missing_consent':r['human_consent']={}
            if change=='agent':r['human_consent']['actor_kind']='codex'
            if change=='wrong_phrase':r['human_consent']['statement']='approved'
            with self.assertRaises((ValueError,PermissionError)):validate_consent_fixture(r,self.context,now=NOW)

    def test_expired_and_future_consent_rejected(self):
        for changes in ({'expires_at':NOW.isoformat()},{'issued_at':(NOW+timedelta(minutes=1)).isoformat()}):
            with self.assertRaises(PermissionError):validate_consent_fixture(dict(self.record,**changes),self.context,now=NOW)

    def test_every_identity_period_terminal_and_resource_change_breaks_binding(self):
        for key in ('manifest_sha256','controls_sha256','scenario_sha256','source_sha256','compiled_sha256','plan_sha256'):
            context=deepcopy(self.context);context[key]='f'*64
            with self.assertRaises((ValueError,PermissionError)):validate_consent_fixture(self.record,context,now=NOW)
        for key in ('terminal','parameters','period','resources'):
            context=deepcopy(self.context)
            if key=='terminal':context[key]['installation_sha256']='e'*64
            if key=='parameters':context[key]['model']='real ticks'
            if key=='period':context[key]['warmup_from']='2026-11-02'
            if key=='resources':context[key]['max_memory_bytes']*=2
            with self.assertRaises((ValueError,PermissionError)):validate_consent_fixture(self.record,context,now=NOW)

    def test_incomplete_context_is_rejected(self):
        c=deepcopy(self.context);del c['compiled_sha256']
        with self.assertRaises(ValueError):validate_consent_fixture(consent_fixture(c),c,now=NOW)

    def test_real_legacy_or_batch_authorizations_are_ineligible(self):
        for changes in ({'fixture_kind':'real'},{'scope':'batch_execution'},{'schema_version':'1.0'}):
            with self.assertRaises(PermissionError):validate_consent_fixture(dict(self.record,**changes),self.context,now=NOW)
        with self.assertRaises(PermissionError):self.store.execute(enabled=True,authorization=self.record)

    def test_atomic_single_use_even_with_another_authorization_id(self):
        self.register();self.consume()
        with self.assertRaises(PermissionError):self.consume()
        other=consent_fixture(self.context,'synthetic-second')
        self.store.register_fixture(other,self.context,now=NOW)
        with self.assertRaises(PermissionError):self.store.consume_fixture(other['authorization_id'],self.context,now=NOW)
        self.assertEqual(self.store.inspect()['counts']['consumptions'],1)

    def test_two_concurrent_consumers_have_exactly_one_winner(self):
        self.register()
        def consume():
            try:self.consume();return True
            except PermissionError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:consume(),range(2)))
        self.assertEqual(sum(results),1);self.assertEqual(self.store.inspect()['counts']['consumptions'],1)

    def test_revocation_before_consumption_is_atomic_and_idempotent(self):
        self.register();self.store.revoke_fixture(self.record['authorization_id'])
        before=self.store.inspect();self.store.revoke_fixture(self.record['authorization_id'])
        self.assertEqual(before,self.store.inspect())
        with self.assertRaises(PermissionError):self.consume()

    def test_revocation_after_consumption_before_start_keeps_consumption(self):
        self.register();receipt=self.consume();self.store.revoke_fixture(self.record['authorization_id'])
        with self.assertRaises(PermissionError):self.store.record_simulated_start(receipt,self.context,now=NOW)
        self.assertEqual(self.store.inspect()['counts']['consumptions'],1)
        self.assertEqual(self.store.inspect()['counts']['starts'],0)

    def test_expiration_rechecked_after_consumption(self):
        self.register();receipt=self.consume()
        with self.assertRaises(PermissionError):self.store.record_simulated_start(receipt,self.context,now=NOW+timedelta(minutes=6))

    def test_duplicate_simulated_start_and_receipt_tampering_rejected(self):
        self.register();receipt=self.consume()
        with self.assertRaises(PermissionError):self.store.record_simulated_start(dict(receipt,context_sha256='0'*64),self.context,now=NOW)
        self.store.record_simulated_start(receipt,self.context,now=NOW)
        with self.assertRaises(PermissionError):self.store.record_simulated_start(receipt,self.context,now=NOW)

    def test_event_persistence_failure_rolls_back_consumption(self):
        self.register();before=self.store.inspect()
        with patch.object(self.store,'_event',side_effect=OSError('SYNTHETIC disk failure')):
            with self.assertRaises(OSError):self.consume()
        self.assertEqual(before,self.store.inspect())

    def test_commit_failure_rolls_back_consumption(self):
        self.register();before=self.store.inspect()
        with patch.object(self.store,'_commit',side_effect=OSError('SYNTHETIC commit failure')):
            with self.assertRaises(OSError):self.consume()
        self.assertEqual(before,self.store.inspect())

    def test_reopen_after_lost_receipt_never_reconsumes_or_autostarts(self):
        self.register();self.consume()  # Receipt lost after durable consumption.
        reopened=ConsentSimulationLedger(self.root,reopen=True)
        self.assertEqual(reopened.inspect()['consumed_without_start_event'],1)
        self.assertFalse(reopened.inspect()['automatic_restart'])
        with self.assertRaises(PermissionError):reopened.consume_fixture(self.record['authorization_id'],self.context,now=NOW)

    def test_incomplete_storage_never_reinitialized(self):
        self.store.path.unlink()
        with self.assertRaises(Exception):ConsentSimulationLedger(self.root,reopen=True)
        with self.assertRaises(Exception):self.consume()
        self.assertFalse(self.store.path.exists())

    def test_registration_is_idempotent_but_identity_cannot_be_overwritten(self):
        self.register();before=self.store.inspect();self.register();self.assertEqual(before,self.store.inspect())
        r=deepcopy(self.record);r['expires_at']=(NOW+timedelta(minutes=7)).isoformat()
        with self.assertRaises(PermissionError):self.store.register_fixture(r,self.context,now=NOW)

    def test_historical_root_cannot_be_reused(self):
        other=Path(self.temp.name)/'historical';other.mkdir();(other/'old.txt').write_text('SYNTHETIC history')
        with self.assertRaises(FileExistsError):ConsentSimulationLedger(other)
        self.assertEqual((other/'old.txt').read_text(),'SYNTHETIC history')


class PeriodPlanningTests(unittest.TestCase):
    def snapshots(self):
        return [read_artifact(ROOT/p) for p in ('runs/phase32h_execution_a7e690b3b483dde0_attempt1/history_preflight_raw.json','runs/phase22_control/history.json','runs/phase23_preparation/ticks.json')]

    def test_real_local_snapshots_when_available_preserve_coverage_only_candidates(self):
        try:snapshots=self.snapshots()
        except FileNotFoundError:self.skipTest('private local snapshots are intentionally not published')
        coverage=inventory_local_history(snapshots);proposal=propose_periods(coverage)
        self.assertEqual(coverage['unique_bars'],1252);self.assertEqual(coverage['observed_tick_records'],0)
        self.assertEqual(proposal['periods']['development']['from_date'],'2026-10-27')
        self.assertEqual(proposal['periods']['out_of_sample']['from_date'],'2026-11-10')
        self.assertIsNone(proposal['periods']['final_test'])
        self.assertEqual([(c['warmup_bars'],c['evaluation_bars']) for c in proposal['candidate_counts']],[(73,330),(94,378)])

    def test_advertised_start_does_not_create_coverage(self):
        c=inventory_local_history([dict(symbol='PETR4',period='M5',ok=True,data_available_from='2000-01-01',history=[])])
        p=propose_periods(c);self.assertEqual(c['unique_bars'],0)
        self.assertTrue(all(v is None for v in p['periods'].values()))

    def test_conflicting_or_misaligned_bars_block_selection(self):
        one=dict(symbol='PETR4',period='M5',ok=True,history=[dict(time='2026-10-26T10:00:00',close=1)])
        two=deepcopy(one);two['history'][0]['close']=2
        with self.assertRaises(ValueError):propose_periods(inventory_local_history([one,two]))
        one['history'][0]['time']='2026-10-26T10:01:00'
        with self.assertRaises(ValueError):propose_periods(inventory_local_history([one]))

    def test_warmup_and_period_leakage_rejected(self):
        periods=read_artifact(ROOT/'config/batches/phase33a.synthetic.json')['periods']
        periods['out_of_sample']['warmup_from']='2026-11-06'
        with self.assertRaises(ValueError):validate_candidate_periods(periods)

    def test_known_results_never_become_final_independent_period(self):
        final=read_artifact(ROOT/'config/batches/phase33a.synthetic.json')['periods']['development']
        with self.assertRaises(ValueError):validate_candidate_periods(dict(development=None,out_of_sample=None,final_test=final))


class ChecklistTests(unittest.TestCase):
    def setUp(self):
        scope=dict(environment='demo',symbol='PETR4',from_date=None,to_date=None,model='every tick')
        self.readiness=assess_readiness({}, {},scope=scope)
        symbol=dict(symbol='PETR4',spread_float=True,swap_mode=0,swap_long=0,swap_short=0,trade_mode_name='full',
            volume_min=100,volume_step=100,tick_size=.01,tick_value=.01,currency_profit='BRL',currency_margin='BRL')
        account=dict(type='demo',currency='BRL',margin_mode='hedging',read_only=False)
        self.metadata=classify_metadata({'symbols':[symbol]},{'account':account},observed_at=NOW.isoformat())
        self.periods=dict(proposal_only=True,live_execution_enabled=False,periods=dict(development=None,out_of_sample=None,final_test=None))
        self.safety={k:True for k in SAFETY_KEYS};self.decisions={k:False for k in DECISIONS}
        self.integration={k:dict(classification='unknown',source_sha256=None) for k in INTEGRATION_EVIDENCE}

    def review(self):return review_checklist(self.readiness,self.periods,metadata=self.metadata,integration_evidence=self.integration,safety=self.safety,decisions=self.decisions)

    def complete_evidence(self):
        self.readiness['source_hashes']={'synthetic-reference':'a'*64}
        for row in self.readiness['checks'].values():row.update(classification='confirmed',evidence=[{'source':'synthetic-reference'}])
        for row in self.metadata['checks'].values():row['classification']='confirmed'
        self.integration={k:dict(classification='confirmed',source_sha256='a'*64) for k in INTEGRATION_EVIDENCE}
        # Artificial criteria-path fixture, not a claim of real observed evidence.
        base=read_artifact(ROOT/'config/batches/phase33a.synthetic.json')['periods']['development']
        for stage,start,end in (('development','2026-01-05','2026-01-10'),('out_of_sample','2026-02-02','2026-02-07'),('final_test','2026-03-02','2026-03-07')):
            self.periods['periods'][stage]=dict(base,from_date=start,to_date=end,warmup_from=start,history_status='verified')

    def test_missing_costs_margin_periods_remain_blocked_despite_human_flags(self):
        self.decisions={k:True for k in DECISIONS}
        result=self.review();self.assertEqual(result['classification'],'BLOCKED_MISSING_EVIDENCE')
        self.assertTrue(any(r['item']=='margin_required' and r['state']=='BLOCKED_MISSING_EVIDENCE' for r in result['checks']))

    def test_safety_has_priority(self):
        self.safety['executor_disabled']=False
        self.assertEqual(self.review()['classification'],'BLOCKED_SAFETY')

    def test_ready_for_review_never_grants_execution(self):
        self.complete_evidence()
        self.assertEqual(self.review()['classification'],'REQUIRES_HUMAN_DECISION')
        self.decisions={k:True for k in DECISIONS};r=self.review()
        self.assertEqual(r['classification'],'READY_FOR_REVIEW')
        self.assertFalse(r['live_execution_enabled']);self.assertFalse(r['authorization_granted'])
        for method in (execution_gate,OperationalTesterAdapter().request):
            with self.assertRaises(PermissionError):method(ready_for_review=True)

    def test_omitted_critical_evidence_is_not_silently_ignored(self):
        del self.readiness['checks']['commission']
        with self.assertRaises(ValueError):self.review()

    def test_empty_evidence_cannot_confirm_critical_checks(self):
        self.complete_evidence();self.decisions={k:True for k in DECISIONS}
        self.readiness['checks']['commission']['evidence']=[]
        self.assertEqual(self.review()['classification'],'BLOCKED_MISSING_EVIDENCE')

    def test_metadata_never_invents_commission_margin_or_account_leverage(self):
        for field in ('commission_per_operation','required_margin','slippage','account_leverage'):
            self.assertIsNone(self.metadata['checks'][field]['value'])
            self.assertEqual(self.metadata['checks'][field]['classification'],'unknown')
        self.assertEqual(self.metadata['checks']['short_rules']['classification'],'partially_confirmed')

    def test_read_only_transport_cannot_start_even_with_new_context(self):
        def forbidden(*args):raise AssertionError('no underlying call permitted')
        transport=HomologationTransport(forbidden)
        with self.assertRaises(PermissionError):transport.start(human_consent=True)

    def test_resource_envelope_uses_audited_elapsed_not_profit(self):
        paths=[ROOT/'runs'/p/'run_summary_1_1_audited.json' for p in ('phase32d_audit_20261121','phase32f_execution_fcb7f99b53c86641_attempt1','phase32h_execution_a7e690b3b483dde0_attempt1')]
        if not all(p.exists() for p in paths):self.skipTest('private audited summaries absent')
        r=assess_resource_proposal([read_artifact(p) for p in paths],ResourcePolicy(timeout_batch_seconds=900))
        self.assertEqual(r['logical_envelope_seconds'],675);self.assertTrue(r['logical_envelope_fits_batch'])
        self.assertAlmostEqual(r['observed_sum_seconds'],43.985)
        self.assertFalse(r['os_cpu_memory_limits_enforced']);self.assertFalse(r['future_duration_forecast_validated'])
        invalid=assess_resource_proposal([read_artifact(p) for p in paths],ResourcePolicy(timeout_attempt_seconds=1,timeout_batch_seconds=1))
        self.assertEqual(invalid['classification'],'incompatible')


if __name__=='__main__':unittest.main()
