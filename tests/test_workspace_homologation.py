import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from strategy_factory import workspace_homologation as h

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceHomologationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'runs/phase33j_h5j_a_20261125/limited_verifier.py'
        spec = importlib.util.spec_from_file_location('phase8_protocol_test', path)
        self.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.core)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tool = json.loads((ROOT / 'tests/fixtures/factory_workspace_tool.json').read_text(encoding='utf-8'))
        self.current = dict(pid=7, start='birth', exe_sha256='pinned', build='5.0.0.6328',
            path=h.EXE, data=h.DATA, origin_matches=True, dedicated_process_unique=True,
            config_pinned=True, terminal_safe=True, listener={'address':'127.0.0.1','port':22355,'pid':7})
        self.expected = copy.deepcopy(self.current)
        self.calls, self.loads = [], []
        self.result = dict(schema_version='1', workspace={'mql5_folder':h.DATA+'/MQL5'},
            permissions={'write_roots':[h.DATA+'/MQL5/Experts']}, compiler={},
            community={'community_login':'DO_NOT_PERSIST_COMMUNITY'}, ide={}, capabilities={}, limits={})
        self.version, self.session, self.response_session = h.VERSION, 'MEMORY_SESSION', 'MEMORY_SESSION'
        self.cursor, self.error, self.text_only, self.http_status = None, False, False, None

    def credentials(self):
        self.assertTrue((self.root/h.GUARD_NAME).exists())
        self.loads.append(True)
        return {'Authorization':'Bearer PRIVATE_SYNTHETIC'}

    def post(self, url, payload, headers):
        self.calls.append(copy.deepcopy((url, payload, headers)))
        method = payload['method']
        body = None
        if method == 'initialize':
            result = {'protocolVersion':self.version,'serverInfo':{'name':'fake','version':'1'},'capabilities':{'tools':{}}}
        elif method == 'notifications/initialized':
            return {'status':202,'headers':{},'body':b''}
        elif method == 'tools/list':
            result = {'tools':[copy.deepcopy(self.tool) if n=='get_workspace_info' else {'name':n} for n in sorted(h.CATALOG)],'nextCursor':self.cursor}
        else:
            result = {'isError':self.error}
            if self.text_only:
                result['content']=[{'type':'text','text':json.dumps(self.result)}]
            else:
                result['structuredContent']=copy.deepcopy(self.result)
        raw = json.dumps({'jsonrpc':'2.0','id':payload['id'],'result':result}).encode()
        return {'status':self.http_status or 200,'headers':{'Content-Type':'application/json',
            'Mcp-Session-Id': self.session if method=='initialize' else self.response_session},'body':raw}

    def attempt(self, confirmation=h.CONFIRMATION):
        return h.WorkspaceAttempt(protocol=self.core, transport=self, identity=lambda:copy.deepcopy(self.current),
            expected=self.expected, credentials=self.credentials, guard=self.root/h.GUARD_NAME,
            guard_root=self.root, confirmation=confirmation, authorization=h.AUTHORIZATION)

    def assert_stops(self, limit, category=None):
        a=self.attempt()
        with self.assertRaises(h.Refused) as caught: a.run()
        if category is not None:
            self.assertEqual(str(caught.exception),category)
        self.assertLessEqual(len(self.calls),limit)
        self.assertTrue(a.closed)
        with self.assertRaises(h.Refused): a.run()
        self.assertIsNone(a.auth)
        return a

    def test_success_exact_sequence_and_privacy(self):
        a=self.attempt(); report=a.run()
        self.assertEqual([p['method'] for _,p,_ in self.calls],['initialize','notifications/initialized','tools/list','tools/call'])
        self.assertEqual(self.calls[-1][1]['params'],{'name':'get_workspace_info','arguments':{}})
        self.assertTrue(report['workspace_homologated'])
        self.assertEqual(report['posts_consumed'],4)
        self.assertEqual(len(self.loads),1)
        for secret in ('DO_NOT_PERSIST_COMMUNITY','PRIVATE_SYNTHETIC','MEMORY_SESSION'):
            self.assertNotIn(secret,json.dumps(report))
        self.assertTrue(a.closed)
        self.assertIsNone(a.auth)

    def test_protocol_and_session_headers(self):
        self.attempt().run()
        self.assertNotIn('MCP-Protocol-Version',self.calls[0][2])
        for _,_,headers in self.calls[1:]:
            self.assertEqual(headers['MCP-Protocol-Version'],h.VERSION)
            self.assertEqual(headers['Mcp-Session-Id'],'MEMORY_SESSION')

    def test_confirmation_required_before_guard_or_credentials(self):
        with self.assertRaises(h.Refused): self.attempt('yes')
        self.assertFalse(list(self.root.iterdir()));self.assertFalse(self.loads);self.assertFalse(self.calls)

    def test_old_guard_not_reused(self):
        p=self.root/h.GUARD_NAME;p.write_text('old guard')
        self.assert_stops(0)
        self.assertEqual(p.read_text(),'old guard');self.assertFalse(self.loads)

    def test_credential_failure_consumes_guard(self):
        def unavailable(): raise RuntimeError('PRIVATE_SYNTHETIC')
        self.credentials=unavailable
        a=self.attempt()
        with self.assertRaisesRegex(h.Refused, '^protected_credential_unavailable$'):
            a.run()
        self.assertTrue(a.closed)
        self.assertFalse(self.calls)
        self.assertTrue((self.root/h.GUARD_NAME).exists())

    def test_identity_drift_blocks_each_field(self):
        original=copy.deepcopy(self.current)
        changes={'pid':8,'start':'changed','exe_sha256':'changed','build':'changed','path':'C:/other.exe',
                 'data':'C:/other','origin_matches':False,'dedicated_process_unique':False,
                 'config_pinned':False,'terminal_safe':False,'listener':{'address':'0.0.0.0','port':22355,'pid':7}}
        for field,value in changes.items():
            with self.subTest(field=field):
                self.current=copy.deepcopy(original);self.current[field]=value
                self.assert_stops(0)
                self.assertFalse(self.loads)

    def test_identity_changes_after_credentials_before_first_send(self):
        old=self.credentials
        def change():
            headers=old();self.current['start']='reused PID';return headers
        self.credentials=change
        self.assert_stops(0)

    def test_identity_changes_before_next_post(self):
        post=self.post
        def change(*args):
            response=post(*args);self.current['start']='changed';return response
        self.post=change
        self.assert_stops(1)

    def test_version_mismatch_no_retry(self):
        self.version='2025-03-26';self.assert_stops(1)

    def test_session_mismatch_no_retry(self):
        self.response_session='CHANGED';self.assert_stops(3)

    def test_http_error_no_retry(self):
        self.http_status=401;self.assert_stops(1)

    def test_pagination_refused(self):
        self.cursor='cursor';self.assert_stops(3)

    def test_changed_definition_blocks_tool_call(self):
        self.tool['description']+=' changed';self.assert_stops(3,'workspace_definition_mismatch')

    def test_changed_nested_schema_blocks_tool_call(self):
        self.tool['outputSchema']['properties']['workspace']['additionalProperties']=True
        self.assert_stops(3)

    def test_catalog_mismatch_blocks_call(self):
        original=self.post
        def changed(url,payload,headers):
            r=original(url,payload,headers)
            if payload['method']=='tools/list':
                envelope=json.loads(r['body']);envelope['result']['tools'][-1]={'name':'unknown_tool'}
                r['body']=json.dumps(envelope).encode()
            return r
        self.post=changed;self.assert_stops(3)

    def test_missing_structured_content_no_text_fallback(self):
        self.text_only=True;self.assert_stops(4)

    def test_tool_error_rejected(self):
        self.error=True;self.assert_stops(4)

    def test_wrong_workspace_rejected(self):
        self.result['workspace']['mql5_folder']='C:/other/MQL5';self.assert_stops(4,'workspace_identity_mismatch')

    def test_write_root_escape_rejected(self):
        self.result['permissions']['write_roots']=['C:/outside'];self.assert_stops(4,'workspace_write_root_outside')

    def test_community_invalid_type_rejected_without_leak(self):
        self.result['community']['community_login']={'secret':'DO_NOT_PERSIST_COMMUNITY'}
        a=self.assert_stops(4,'workspace_schema_violation')
        self.assertNotIn('DO_NOT_PERSIST_COMMUNITY',json.dumps(a.summary()))

    def test_bool_as_build_rejected(self):
        self.result['compiler']['compiler_mql5_build']=True;self.assert_stops(4)

    def test_additional_result_property_rejected(self):
        self.result['unexpected']='DO_NOT_PERSIST_COMMUNITY';self.assert_stops(4)

    def test_guard_path_cannot_select_historical_guard(self):
        with self.assertRaises(h.Refused):
            h.WorkspaceAttempt(protocol=self.core,transport=self,identity=lambda:self.current,
                expected=self.expected,credentials=self.credentials,guard=self.root/'H5JD_attempt_consumed.flag',
                guard_root=self.root,confirmation=h.CONFIRMATION,authorization=h.AUTHORIZATION)
