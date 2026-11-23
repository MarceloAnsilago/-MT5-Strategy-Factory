"""Authorized history transport regression, entirely offline and finite."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.history_transport import (
    AuthorizedHistoryTransport, PLAN_SHA256, VALID_FROM, VALID_TO, check_window,
    verify_identity, approval_scope)

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime.fromisoformat(VALID_FROM)+timedelta(minutes=5)


def plan(): return read_artifact(ROOT/'config/history/phase33f.proposal.json')


def identity(moment=NOW):
    return dict(connection=plan()['connection'],symbol='PETR4',observed_at=moment.isoformat(),
        source='MCP_workspace_account_marketwatch',live_execution_enabled=False)


def response(request, **changes):
    prefix=request['datetime_from'][:10]
    def bar(minute, **values):
        return dict(dict(time=f'{prefix}T10:{minute:02}:00+00:00',open=10,high=12,low=9,close=11,
                         tick_volume=10,volume=100,spread=1),**values)
    rows=[bar(i) for i in range(5)] if request['period']=='M1' else [bar(0,tick_volume=50,volume=500)]
    payload=dict(ok=True,symbol='PETR4',period=request['period'],history=rows,
        complete=True,timezone='UTC',connection=plan()['connection'],
        datetime_from=request['datetime_from'],datetime_to=request['datetime_to'])
    payload.update(changes)
    return dict(content=[dict(type='text',text=json.dumps(payload,ensure_ascii=False))],isError=False)


class ClockWindow(unittest.TestCase):
    def test_exact_start_inclusive_end_exclusive_and_naive_clock_rejected(self):
        check_window(datetime.fromisoformat(VALID_FROM))
        check_window(datetime.fromisoformat(VALID_TO)-timedelta(microseconds=1))
        for moment in (datetime.fromisoformat(VALID_FROM)-timedelta(microseconds=1),datetime.fromisoformat(VALID_TO)):
            with self.assertRaises(PermissionError):check_window(moment)
        with self.assertRaises(ValueError):check_window(datetime(2026,11,24,12))

    def test_approval_scope_is_acquisition_only_and_binds_original_plan(self):
        self.assertEqual(fingerprint(plan()),PLAN_SHA256)
        scope=approval_scope()
        self.assertEqual(scope['tools'],['get_chart_history']);self.assertFalse(scope['live_execution_enabled'])
        self.assertEqual(scope['timeframes'],['M1','M5'])


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.session=AuthorizedHistoryTransport(plan(),base_root=self.base)
        self.calls=[]

    def invoke(self, session=None, **kwargs):
        def tool(name,request):
            self.calls.append((name,request));return response(request)
        return (session or self.session).acquire_next(tool,identity(),now=lambda:NOW,free_bytes=lambda:10**12,**kwargs)

    def test_before_window_no_dispatch_or_intent(self):
        before=datetime.fromisoformat(VALID_FROM)-timedelta(seconds=1)
        with self.assertRaisesRegex(PermissionError,'AWAITING'):
            self.session.acquire_next(lambda *args:self.fail('dispatch'),identity(before),now=lambda:before)
        self.assertEqual(self.session.status(now=before)['history_calls'],0)
        self.assertEqual(self.session.status(now=before)['state'],'AWAITING_AUTHORIZATION_WINDOW')

    def test_expired_window_no_dispatch(self):
        end=datetime.fromisoformat(VALID_TO)
        with self.assertRaisesRegex(PermissionError,'EXPIRED'):
            self.session.acquire_next(lambda *args:self.fail('dispatch'),identity(end),now=lambda:end)

    def test_changed_original_plan_is_rejected_without_storage(self):
        changed=plan();changed['max_calls']-=1
        with self.assertRaises(PermissionError):AuthorizedHistoryTransport(changed,base_root=self.base/'other')
        self.assertFalse((self.base/'other').exists())

    def test_only_history_tool_is_dispatched_and_original_mcp_text_bytes_are_saved(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            receipt=self.invoke()
        self.assertEqual(self.calls[0][0],'get_chart_history')
        request=self.calls[0][1]
        self.assertEqual(request['datetime_from'],'2024-01-02T00:00:00')
        self.assertEqual(request['limit'],2000)
        saved=(self.session.root/'call-000000/response.txt').read_bytes()
        self.assertEqual(saved,response(request)['content'][0]['text'].encode('utf-8'))
        self.assertEqual(receipt['record_count'],5);self.assertFalse(receipt['live_execution_enabled'])

    def test_pilot_is_four_calls_and_scale_requires_explicit_review(self):
        for _ in range(4):self.invoke()
        with self.assertRaisesRegex(PermissionError,'PILOT_REVIEW_REQUIRED'):self.invoke()
        self.assertEqual(len(self.calls),4)
        self.session.accept_pilot()
        self.invoke()
        self.assertEqual(self.calls[-1][1]['datetime_from'],'2024-01-01T00:00:00')
        self.assertEqual(self.session.status(now=NOW)['history_calls'],5)

    def test_resume_never_repeats_pilot_pages(self):
        self.invoke()
        reopened=AuthorizedHistoryTransport(plan(),base_root=self.base)
        self.invoke(reopened)
        self.assertEqual(self.calls[1][1]['period'],'M5')
        self.assertNotEqual(self.calls[0][1],self.calls[1][1])

    def test_failed_connection_is_durable_and_never_retried(self):
        calls=[]
        def disconnected(*args):calls.append(args);raise ConnectionError('synthetic disconnect')
        with self.assertRaises(ConnectionError):
            self.session.acquire_next(disconnected,identity(),now=lambda:NOW,free_bytes=lambda:10**12)
        reopened=AuthorizedHistoryTransport(plan(),base_root=self.base)
        with self.assertRaisesRegex(PermissionError,'ACQUISITION_BLOCKED'):self.invoke(reopened)
        self.assertEqual(len(calls),1)
        self.assertEqual(reopened.status(now=NOW)['history_calls'],1)

    def test_unknown_rpc_outcome_without_receipt_blocks_new_worker(self):
        # Failing receipt storage is injected after durable intent.
        import strategy_factory.history_transport as module
        original=module._save
        def save(path,data):
            if path.name in ('failure.json','receipt.json'):raise OSError('disk failure')
            original(path,data)
        with patch.object(module,'_save',save):
            with self.assertRaises(OSError):
                self.session.acquire_next(lambda *args:(_ for _ in ()).throw(ConnectionError()),
                    identity(),now=lambda:NOW,free_bytes=lambda:10**12)
        reopened=AuthorizedHistoryTransport(plan(),base_root=self.base)
        self.assertIn('pending_or_unknown_call_outcome',reopened.status(now=NOW)['blockers'])
        with self.assertRaises(PermissionError):self.invoke(reopened)

    def test_second_worker_cannot_dispatch_while_first_intent_is_pending(self):
        def tool(name,request):
            second=AuthorizedHistoryTransport(plan(),base_root=self.base)
            with self.assertRaises(PermissionError):self.invoke(second)
            return response(request)
        self.session.acquire_next(tool,identity(),now=lambda:NOW,free_bytes=lambda:10**12)

    def test_stale_future_or_divergent_identity_blocks_before_dispatch(self):
        for changes in (dict(observed_at=(NOW-timedelta(seconds=61)).isoformat()),
                        dict(observed_at=(NOW+timedelta(seconds=1)).isoformat()),
                        dict(connection=dict(plan()['connection'],build=6231)),dict(symbol='PETR3')):
            with self.subTest(changes=changes),self.assertRaises(PermissionError):
                self.session.acquire_next(lambda *a:self.fail('dispatch'),dict(identity(),**changes),now=lambda:NOW,free_bytes=lambda:10**12)

    def test_disk_and_interrupt_limits_block_before_dispatch(self):
        with self.assertRaises(OSError):
            self.session.acquire_next(lambda *a:self.fail('dispatch'),identity(),now=lambda:NOW,free_bytes=lambda:0)
        with self.assertRaises(PermissionError):self.invoke(stop=lambda:True)
        self.assertEqual(self.session.calls,0)

    def test_window_expiring_in_flight_preserves_response_and_blocks_continuation(self):
        current=[NOW]
        def tool(name,request):current[0]=datetime.fromisoformat(VALID_TO);return response(request)
        with self.assertRaisesRegex(PermissionError,'EXPIRED'):
            self.session.acquire_next(tool,identity(),now=lambda:current[0],free_bytes=lambda:10**12)
        self.assertTrue((self.session.root/'call-000000/response.txt').exists())
        self.assertEqual(self.session.status(now=NOW)['state'],'ACQUISITION_BLOCKED')

    def test_ambiguity_empty_incomplete_scope_conflict_or_missing_timezone_stops_first_call(self):
        cases=[dict(history=[]),dict(complete=False),dict(timezone=None),dict(symbol='OTHER'),
               dict(connection=None),dict(datetime_to=None)]
        for index,changes in enumerate(cases):
            with self.subTest(changes=changes):
                session=AuthorizedHistoryTransport(plan(),base_root=self.base/str(index))
                with self.assertRaises(ValueError):
                    session.acquire_next(lambda name,request:response(request,**changes),identity(),now=lambda:NOW,free_bytes=lambda:10**12)
                with self.assertRaises(PermissionError):self.invoke(session)
                self.assertEqual(session.calls,1)

    def test_oversize_keeps_bounded_prefix_and_hash_without_more_calls(self):
        text='x'*(2*1024*1024+1)
        with self.assertRaisesRegex(ValueError,'2 MiB'):
            self.session.acquire_next(lambda *a:dict(content=[dict(type='text',text=text)]),identity(),now=lambda:NOW,free_bytes=lambda:10**12)
        self.assertEqual((self.session.root/'call-000000/response.txt').stat().st_size,2*1024*1024)
        self.assertTrue(read_artifact(self.session.root/'call-000000/failure.json')['stored_prefix_only'])

    def test_stored_response_tampering_prevents_resume(self):
        self.invoke();path=self.session.root/'call-000000/response.txt';path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'bytes changed'):AuthorizedHistoryTransport(plan(),base_root=self.base)

    def test_mcp_error_and_nontext_envelope_are_not_success(self):
        for index,result in enumerate((dict(isError=True,content=[dict(type='text',text='{}')]),dict(structuredContent={}))):
            session=AuthorizedHistoryTransport(plan(),base_root=self.base/str(index))
            with self.assertRaises(ValueError):session.acquire_next(lambda *a:result,identity(),now=lambda:NOW,free_bytes=lambda:10**12)
            receipt=read_artifact(session.root/'call-000000/receipt.json')
            self.assertEqual(receipt['outcome'],'failed')

    def test_processing_deadline_after_response_is_failure(self):
        ticks=iter([0,0,21600,21600])
        with self.assertRaises(TimeoutError):self.invoke(clock=lambda:next(ticks))
        self.assertTrue((self.session.root/'call-000000/response.txt').exists())

    def test_record_storage_and_call_caps_are_checked_before_rpc(self):
        # Persistent counters are reloaded, so tampering with instance fields
        # cannot loosen an approved cap. The immutable plan rejects changes.
        self.session.calls=999999
        self.invoke()
        self.assertEqual(self.session.calls,1)
        self.assertEqual(self.session.plan['max_calls'],2100)
        self.assertEqual(self.session.plan['max_records'],1800000)

    def test_each_exhausted_resource_budget_blocks_dispatch(self):
        original=self.session.reload
        for attribute,value,error in [('calls',2100,PermissionError),('elapsed',21600,PermissionError),
                                       ('records',1800000,PermissionError),('storage',2147483648,OSError)]:
            def reload():
                original();setattr(self.session,attribute,value)
            with self.subTest(attribute=attribute),patch.object(self.session,'reload',reload),self.assertRaises(error):
                self.invoke()
        self.assertFalse(self.calls)

    def test_plan_or_session_mutation_after_open_cannot_enable_tools(self):
        self.session.plan['max_calls']+=1
        with self.assertRaises(PermissionError):self.invoke()
        self.assertFalse(self.calls)

    def test_diagnostic_attempts_are_also_persisted_in_total_call_budget(self):
        self.session.record_diagnostic('rico_terminal.get_workspace_info',observed_at=NOW.isoformat())
        self.invoke()
        reopened=AuthorizedHistoryTransport(plan(),base_root=self.base)
        self.assertEqual(reopened.status(now=NOW)['total_mcp_calls'],2)
        with self.assertRaises(PermissionError):
            reopened.record_diagnostic('tester_run_backtest',observed_at=NOW.isoformat())


class IdentityTests(unittest.TestCase):
    def test_observation_is_sanitized_and_installation_bound(self):
        path=r'C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B\MQL5'
        workspace=dict(workspace=dict(mql5_folder=path),compiler=dict(compiler_mql5_build=6230))
        account=dict(account=dict(server='Rico-DEMO',type='demo',login='private',name='private'),
            terminal=dict(build=6230,server_connected=True,program_name='Rico - MetaTrader 5'))
        symbols=dict(symbols=[dict(symbol='PETR4',selected=True)])
        result=verify_identity(plan(),workspace,account,symbols,observed_at=NOW.isoformat())
        self.assertEqual(result,identity())
        self.assertNotIn('private',json.dumps(result))
        account['terminal']['server_connected']=False
        with self.assertRaises(PermissionError):verify_identity(plan(),workspace,account,symbols,observed_at=NOW.isoformat())


if __name__=='__main__':unittest.main()
