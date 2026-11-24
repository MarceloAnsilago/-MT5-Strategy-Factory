"""Connection architecture tests: finite fixtures, no terminal import or IPC."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.batch_manifest import fingerprint
from strategy_factory.python_history_adapter import INSTALLATION, proposal
from strategy_factory.python_connection_bridge import (ROOT, PreparedPythonBridge,
    diagnostic_proposal, validate_process_attestation, RecordedConnectionPort,
    ConnectionDiagnosticLab,CrossBackendAttemptIndex)

NOW=datetime(2026,11,24,18,tzinfo=timezone.utc)
DATA=r'C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B'
EXE=INSTALLATION+r'\terminal64.exe'


def evidence():
    return dict(exe=EXE,resolved_exe=EXE,exe_sha256='a'*64,expected_exe_sha256='a'*64,
        file_id='synthetic-volume-file',expected_file_id='synthetic-volume-file',
        resolved_data_path=DATA,reparse_detected=False,observed_at=NOW.isoformat(),
        processes=[dict(pid=42,exe=EXE,file_id='synthetic-volume-file',data_path=DATA,
            started_at=(NOW-timedelta(hours=1)).isoformat())])


def consent():
    return dict(purpose='synthetic_connection_only',plan_sha256=fingerprint(diagnostic_proposal()),
        from_utc=NOW.isoformat(),to_utc=(NOW+timedelta(minutes=5)).isoformat(),
        account_binding='synthetic-demo-account')


def sequence():
    values=[('initialize',True),
        ('terminal_info',dict(path=INSTALLATION,data_path=DATA,build=6230,name='Rico - MetaTrader 5',connected=True)),
        ('account_info',dict(server='Rico-DEMO',trade_mode=0,binding='synthetic-demo-account')),
        ('symbol_info',dict(name='PETR4',select=True,custom=False)),('shutdown',None)]
    return [item for name,value in values for item in ((name,value),('last_error',(1,'synthetic ok')))]


class BridgeContracts(unittest.TestCase):
    def test_every_native_method_is_blocked_even_with_approval_or_mutated_flags(self):
        port=PreparedPythonBridge();port.acquisition_enabled=True
        for name in ('initialize','terminal_info','account_info','symbol_info','copy_rates_range','last_error','shutdown'):
            with self.subTest(name=name),self.assertRaisesRegex(PermissionError,'DISABLED'):
                getattr(port,name)(approved=True)

    def test_diagnostic_proposal_contains_no_history_or_permission(self):
        plan=diagnostic_proposal()
        published=Path(__file__).resolve().parents[1]/'config/history/python_mt5.connection-diagnostic.proposal.json'
        self.assertEqual(json.loads(published.read_text(encoding='utf-8')),plan)
        self.assertFalse(plan['history_queries_allowed']);self.assertFalse(plan['allow_terminal_launch'])
        self.assertIsNone(plan['account_binding']);self.assertIsNone(plan['valid_from'])
        self.assertNotIn('copy_rates_range',plan['allowed_functions'])
        self.assertFalse(plan['native_attach_only_guaranteed'])

    def test_wrong_executable_data_file_identity_reparse_or_multiple_processes_rejected(self):
        for key,value in [('exe',r'C:\Other\terminal64.exe'),('resolved_exe',r'C:\Other\terminal64.exe'),
            ('exe_sha256','b'*64),('file_id','other'),('resolved_data_path',r'C:\Other'),
            ('reparse_detected',True),('processes',[]),('processes',evidence()['processes']*2)]:
            item=evidence();item[key]=value
            with self.subTest(key=key),self.assertRaises(PermissionError):validate_process_attestation(item)


class DiagnosticLabTests(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'diagnostic'
        self.lab=ConnectionDiagnosticLab(self.root,consent(),now=NOW)

    def run_sequence(self,items=None,**kwargs):
        port=RecordedConnectionPort(sequence() if items is None else items)
        report=self.lab.run(port,evidence(),now=lambda:NOW,**kwargs)
        return port,report

    def test_connection_fixture_uses_explicit_executable_pairs_errors_and_shuts_down(self):
        port,report=self.run_sequence()
        self.assertEqual(report['state'],'SYNTHETIC_DIAGNOSTIC_CHECKED')
        self.assertEqual(port.calls,[name for name,_ in sequence()])
        self.assertEqual(port.arguments[0],dict(path=EXE,timeout=5000,portable=False))
        self.assertEqual(report['operations_reserved'],10)
        self.assertFalse(report['acquisition_enabled'])
        self.assertNotIn('binding',json.dumps(report))

    def test_native_port_callback_or_subclass_cannot_be_injected(self):
        class Derived(RecordedConnectionPort):pass
        for port in (PreparedPythonBridge(),lambda:None,Derived(sequence())):
            with self.assertRaises(PermissionError):self.lab.run(port,evidence(),now=lambda:NOW)

    def test_missing_old_or_real_authorization_refused_before_storage(self):
        from strategy_factory.history_transport import approval_scope
        for i,c in enumerate(({},approval_scope(),dict(consent(),purpose='real_approved'))):
            root=Path(self.temp.name)/str(i)
            with self.assertRaises((ValueError,PermissionError)):ConnectionDiagnosticLab(root,c,now=NOW)
            self.assertFalse(root.exists())

    def test_expired_or_stale_evidence_refused_before_initialization(self):
        port=RecordedConnectionPort(sequence());item=evidence();item['observed_at']=(NOW-timedelta(seconds=6)).isoformat()
        with self.assertRaises(PermissionError):self.lab.run(port,item,now=lambda:NOW)
        self.assertFalse(port.calls)

    def test_initialization_refused_has_no_metadata_and_attempts_cleanup(self):
        items=[('initialize',False),('last_error',(-6,'private credential')),('shutdown',None),('last_error',(1,'ok'))]
        port,report=self.run_sequence(items)
        self.assertEqual(report['state'],'BLOCKED');self.assertNotIn('terminal_info',port.calls)
        self.assertEqual(port.calls[-2: ],['shutdown','last_error'])
        self.assertEqual(report['events'][0]['last_error']['code'],-6)
        self.assertNotIn('private credential',json.dumps(report))

    def test_false_initialize_and_last_error_exception_are_never_success(self):
        for i,error in enumerate(((1,'success'),RuntimeError('private error'))):
            lab=ConnectionDiagnosticLab(Path(self.temp.name)/str(i),consent(),now=NOW)
            items=[('initialize',False),('last_error',error),('shutdown',None),('last_error',(1,'ok'))]
            report=lab.run(RecordedConnectionPort(items),evidence(),now=lambda:NOW)
            self.assertEqual(report['state'],'BLOCKED');self.assertIsNone(report['cleanup_error_type'])
            self.assertNotIn('private error',json.dumps(report))

    def test_wrong_terminal_build_server_demo_or_unbound_account_blocks_with_cleanup(self):
        for index,key,value in [(2,'path',r'C:\Other'),(2,'build',6231),(4,'server','Other'),
                                (4,'trade_mode',2),(4,'binding',None)]:
            root=Path(self.temp.name)/('case-'+key)
            lab=ConnectionDiagnosticLab(root,consent(),now=NOW)
            items=sequence();items[index][1][key]=value
            report=lab.run(RecordedConnectionPort(items),evidence(),now=lambda:NOW)
            self.assertEqual(report['state'],'BLOCKED');self.assertIsNone(report['cleanup_error_type'])

    def test_empty_metadata_and_malformed_last_error_are_structured_failures(self):
        for i,replacement in [(2,('terminal_info',None)),(1,('last_error',('bad','private')))]:
            lab=ConnectionDiagnosticLab(Path(self.temp.name)/str(i),consent(),now=NOW)
            items=sequence();items[i]=replacement
            # Failure at metadata leaves later fixture entries; cleanup refuses
            # their wrong order rather than pretending it succeeded.
            report=lab.run(RecordedConnectionPort(items),evidence(),now=lambda:NOW)
            self.assertEqual(report['state'],'BLOCKED')
            self.assertIsNotNone(report['primary_error_type'])

    def test_stop_before_init_or_after_identity_never_enables_history(self):
        port=RecordedConnectionPort(sequence())
        with self.assertRaises(PermissionError):self.lab.run(port,evidence(),now=lambda:NOW,stop=lambda:True)
        self.assertFalse(port.calls)
        signals=iter([False,False,False,False,False,True])
        _,report=self.run_sequence(stop=lambda:next(signals))
        self.assertEqual(report['state'],'BLOCKED');self.assertIsNone(report['cleanup_error_type'])

    def test_timeout_preserves_failure_and_shutdown_reserve(self):
        ticks=iter([0,0,0,6,6,6,6,6])
        port,report=self.run_sequence(clock=lambda:next(ticks))
        self.assertEqual(report['state'],'BLOCKED')
        self.assertEqual(report['primary_error_type'],'TimeoutError')
        self.assertIn('shutdown',port.calls)

    def test_no_space_or_operation_budget_prevents_initialize(self):
        port,report=self.run_sequence(free_bytes=lambda:0)
        self.assertFalse(port.calls);self.assertEqual(report['state'],'BLOCKED')
        import strategy_factory.python_connection_bridge as module
        original=diagnostic_proposal()
        original['limits']['max_operations']=1
        root=Path(self.temp.name)/'cap'
        with patch.object(module,'diagnostic_proposal',return_value=original):
            c=consent();c['plan_sha256']=fingerprint(original)
            lab=ConnectionDiagnosticLab(root,c,now=NOW)
            port=RecordedConnectionPort(sequence());report=lab.run(port,evidence(),now=lambda:NOW)
            self.assertFalse(port.calls);self.assertEqual(report['state'],'BLOCKED')

    def test_diagnostic_cannot_be_repeated_in_same_directory(self):
        self.run_sequence()
        with self.assertRaises(PermissionError):self.run_sequence()


class GlobalIndexTests(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_same_window_cannot_be_repeated_by_switching_backend_or_plan(self):
        index=CrossBackendAttemptIndex(self.root/'index');page=proposal()['pages'][0]
        index.reserve_synthetic(page,backend='mcp',context_sha256='a'*64)
        reopened=CrossBackendAttemptIndex(self.root/'index')
        with self.assertRaises(PermissionError):reopened.reserve_synthetic(page,backend='python_mt5',context_sha256='b'*64)

    def test_overlapping_window_is_not_new_but_half_open_adjacent_window_is(self):
        index=CrossBackendAttemptIndex(self.root/'index');page=proposal()['pages'][0]
        index.reserve_synthetic(page,backend='python_mt5',context_sha256='a'*64)
        overlap=dict(page,to_utc='2026-11-03T13:10:00+00:00')
        with self.assertRaises(PermissionError):index.reserve_synthetic(overlap,backend='mcp',context_sha256='b'*64)
        index.reserve_synthetic(proposal()['pages'][2],backend='mcp',context_sha256='c'*64)

    def test_unknown_broker_timezone_blocks_conservatively_and_source_is_not_modified(self):
        source=self.root/'prior.json'
        raw=json.dumps(dict(request=dict(symbol='PETR4',period='M1',datetime_from='2026-11-03T00:00:00',datetime_to='2026-11-04T00:00:00'))).encode()
        source.write_bytes(raw)
        index=CrossBackendAttemptIndex(self.root/'index',[source])
        with self.assertRaises(PermissionError):index.reserve_synthetic(proposal()['pages'][0],backend='python_mt5',context_sha256='a'*64)
        self.assertEqual(source.read_bytes(),raw)
        source.write_bytes(raw+b' ')
        with self.assertRaises(PermissionError):index.reserve_synthetic(proposal()['pages'][0],backend='python_mt5',context_sha256='a'*64)

    def test_missing_database_is_not_recreated_and_unknown_source_blocks(self):
        index=CrossBackendAttemptIndex(self.root/'index')
        # Simulate unavailable storage without deleting any receipt/database.
        original=Path.is_file
        with patch.object(Path,'is_file',lambda p:False if p==index.path else original(p)):
            with self.assertRaises(PermissionError):CrossBackendAttemptIndex(self.root/'index')
        source=self.root/'unknown.json';source.write_text('{}')
        unknown=CrossBackendAttemptIndex(self.root/'unknown',[source])
        with self.assertRaises(PermissionError):unknown.reserve_synthetic(proposal()['pages'][0],backend='python_mt5',context_sha256='a'*64)

    def test_existing_adapter_consumes_shared_index_before_recorded_source(self):
        from test_python_history_adapter import consent as history_consent,replies,NOW as HISTORY_NOW
        from strategy_factory.python_history_adapter import LAB_ROOT,OfflinePythonHistoryAdapter,RecordedPythonSource
        index=CrossBackendAttemptIndex(self.root/'index')
        LAB_ROOT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LAB_ROOT) as directory:
            first=OfflinePythonHistoryAdapter(Path(directory)/'one',proposal(),history_consent(),now=HISTORY_NOW,attempt_index=index)
            source=RecordedPythonSource(replies())
            first.acquire_next(source,now=lambda:HISTORY_NOW,free_bytes=lambda:10**12)
            second=OfflinePythonHistoryAdapter(Path(directory)/'two',proposal(),history_consent(),now=HISTORY_NOW,attempt_index=index)
            with self.assertRaises(PermissionError):second.acquire_next(source,now=lambda:HISTORY_NOW,free_bytes=lambda:10**12)
            self.assertEqual(len(source.calls),1)
            first.attempt_index=None
            with self.assertRaisesRegex(PermissionError,'detached'):first.acquire_next(source,now=lambda:HISTORY_NOW,free_bytes=lambda:10**12)


if __name__=='__main__':unittest.main()
