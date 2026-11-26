"""Single-use workspace acceptance adapter. Import performs no I/O.

Protocol decoding and HTTP transport are injected from the preserved H5JC
implementation. No legacy verifier is patched or its classification overridden.
This distinct policy accepts only the exact contract reviewed in workspace_review.
"""
import copy
import json
import re
from pathlib import Path

from strategy_factory.workspace_review import review_definition, validate_workspace_result

CONFIRMATION = 'Autorizo a consulta de workspace pela ferramenta apresentada.'
AUTHORIZATION = 'new_workspace_mcp_session_and_one_reviewed_call'
VERSION = '2025-06-18'
URL = 'http://127.0.0.1:22355/mcp'
GUARD_NAME = 'PHASE8_workspace_attempt_consumed.flag'
DATA = 'C:/Users/User/AppData/Roaming/MetaQuotes/Terminal/AEF1E6F57078EAB3775179FCBD94D671'
EXE = 'C:/estrategia/infra/mt5-factory/MetaEditor64.exe'
CATALOG = frozenset(('get_workspace_info', 'get_time_information', 'list_directory',
    'find_files_by_glob', 'find_files_by_name_keyword', 'read_file', 'read_binary_file',
    'read_file_by_lines', 'create_new_folder', 'create_new_file', 'write_file',
    'write_binary_file', 'delete_file', 'replace_text_in_file', 'search_text',
    'search_regex', 'send_web_request', 'compile_file', 'build_project',
    'syntax_check', 'format_source_code', 'open_file_in_editor', 'list_open_documents'))


class Refused(Exception):
    """Only fixed local categories may escape, never server/credential values."""


def require(condition, category):
    if not condition:
        raise Refused(category)


def norm(value):
    return value.replace('\\', '/').rstrip('/').casefold() if isinstance(value, str) else ''


def validate_identity(current, expected):
    require(type(current) is dict and type(expected) is dict, 'identity_unavailable')
    for field in ('pid', 'start', 'exe_sha256', 'build'):
        require(bool(expected.get(field)) and current.get(field) == expected[field], 'process_identity_changed')
    require(norm(current.get('path')) == norm(EXE), 'executable_path_mismatch')
    require(norm(current.get('data')) == norm(DATA) and current.get('origin_matches') is True,
            'data_origin_mismatch')
    require(current.get('listener') == {'address': '127.0.0.1', 'port': 22355, 'pid': expected['pid']},
            'listener_mismatch')
    require(current.get('dedicated_process_unique') is True, 'ambiguous_process')
    require(current.get('config_pinned') is True and current.get('terminal_safe') is True,
            'configuration_or_terminal_safety_mismatch')


class WorkspaceAttempt:
    """Four POST state machine, zero retries; an absolute six POST ceiling.

    Caller supplies pinned local identity and reviewed protocol dependencies.
    A failed run closes permanently. Guard is durable before credentials/network.
    """
    def __init__(self, *, protocol, transport, identity, expected, credentials,
                 guard, guard_root, confirmation, authorization):
        self.protocol, self.transport = protocol, transport
        self.identity, self.expected, self.credentials = identity, copy.deepcopy(expected), credentials
        self.guard, root = Path(guard), Path(guard_root).resolve()
        require(self.guard.name == GUARD_NAME and self.guard.resolve().parent == root, 'guard_location_rejected')
        require(not self.guard.is_symlink() and not root.is_symlink(), 'guard_link_rejected')
        require(confirmation == CONFIRMATION and authorization == AUTHORIZATION, 'explicit_confirmation_required')
        self.count, self.events, self.closed, self.claimed = 0, [], False, False
        self.auth, self.session, self.version = None, None, None
        self.workspace_sent, self.identity_confirmed = False, False

    def _post(self, method, params=None):
        methods = ('initialize', 'notifications/initialized', 'tools/list', 'tools/call')
        require(not self.closed and self.count < 6 and self.count < len(methods)
                and methods[self.count] == method, 'post_sequence_or_budget_refused')
        validate_identity(self.identity(), self.expected)
        if not self.claimed:
            # No exists-then-write: exclusive creation persists across a crash.
            import os
            try:
                with self.guard.open('x', encoding='ascii') as stream:
                    stream.write('Phase 8 workspace attempt consumed. No retry or reuse.\n')
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                raise Refused('attempt_already_consumed') from None
            self.claimed = True
            try:
                self.auth = self.credentials()
            except Exception:
                raise Refused('protected_credential_unavailable') from None
            require(type(self.auth) is dict and set(self.auth) == {'Authorization'}
                    and isinstance(self.auth['Authorization'], str)
                    and re.fullmatch(r'Bearer [A-Za-z0-9\-._~+/]+=*', self.auth['Authorization']) is not None,
                    'credential_format')
        headers = dict(self.auth)
        headers.update({'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})
        if self.version:
            headers['MCP-Protocol-Version'] = self.version
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        self.protocol.validate_http_context(method, headers, self.version, self.session)
        payload = {'jsonrpc': '2.0', 'method': method}
        notification = method == 'notifications/initialized'
        request_id = None if notification else self.count + 1
        if not notification:
            payload['id'] = request_id
        if params is not None:
            payload['params'] = params
        # Recheck after credential loading, immediately before first send as well.
        validate_identity(self.identity(), self.expected)
        self.count += 1
        if method == 'tools/call':
            self.workspace_sent = True
        response = self.transport.post(URL, payload, headers)
        status = response.get('status')
        require(type(status) is int, 'invalid_http_status')
        self.events.append({'method': method, 'status': status})
        result, returned = self.protocol.decode_response(response, request_id, notification)
        session = returned.get('mcp-session-id')
        if method == 'initialize':
            if session is not None:
                require(isinstance(session, str) and 0 < len(session) <= 4096
                        and all(0x21 <= ord(c) <= 0x7e for c in session), 'invalid_session')
            self.session = session
        elif session is not None:
            require(session == self.session, 'session_changed')
        return result

    def run(self):
        require(not self.closed, 'attempt_closed')
        try:
            result = self._post('initialize', {'protocolVersion': VERSION, 'capabilities': {},
                           'clientInfo': {'name': 'factory-workspace-phase8', 'version': '1'}})
            require(result.get('protocolVersion') == VERSION, 'negotiated_version_mismatch')
            info = result.get('serverInfo')
            require(type(info) is dict and isinstance(info.get('name'), str)
                    and isinstance(info.get('version'), str), 'invalid_server_info')
            caps = result.get('capabilities')
            require(type(caps) is dict and type(caps.get('tools')) is dict, 'tools_capability_missing')
            self.version = VERSION
            self._post('notifications/initialized')
            result = self._post('tools/list', {})
            require(result.get('nextCursor') is None, 'pagination_forbidden')
            tools = result.get('tools')
            require(type(tools) is list and len(tools) == len(CATALOG), 'catalog_mismatch')
            require(all(type(t) is dict and isinstance(t.get('name'), str) for t in tools), 'invalid_catalog')
            require({t['name'] for t in tools} == CATALOG, 'catalog_mismatch')
            tool = next(t for t in tools if t['name'] == 'get_workspace_info')
            try:
                review_definition(tool)  # Complete exact definition, no field projection.
            except ValueError:
                raise Refused('workspace_definition_mismatch') from None
            result = self._post('tools/call', {'name': 'get_workspace_info', 'arguments': {}})
            require(result.get('isError', False) is False, 'tool_execution_error')
            data = result.get('structuredContent')
            require(type(data) is dict, 'structured_content_required')
            try:
                projection = validate_workspace_result(data, expected_mql5=DATA + '/MQL5')
            except ValueError as error:
                # Whitelist fixed local validator messages. Never emit arbitrary
                # exception text, response values, Community or raw paths.
                categories = {
                    'Workspace result violates the observed output schema.': 'workspace_schema_violation',
                    'Workspace MQL5 folder differs from the expected installation.': 'workspace_identity_mismatch',
                    'Workspace write root is outside the expected MQL5 folder.': 'workspace_write_root_outside',
                    'Invalid workspace path.': 'workspace_invalid_path',
                    'Invalid expected MQL5 path.': 'expected_workspace_path_invalid',
                }
                raise Refused(categories.get(str(error), 'workspace_validation_failed')) from None
            self.identity_confirmed = projection['identity_confirmed']
            return self.summary()
        except Refused:
            raise
        except ValueError:
            raise Refused('contract_or_workspace_validation_failed') from None
        except Exception:
            raise Refused('local_protocol_or_transport_failure') from None
        finally:
            self.closed = True
            self.auth, self.session = None, None
            # The retained HTTP implementation also holds a session reference.
            if hasattr(self.transport, 'session'):
                self.transport.session = None

    def summary(self):
        return {'posts_consumed': self.count, 'events': copy.deepcopy(self.events),
                'guard_consumed': self.claimed, 'workspace_call_sent': self.workspace_sent,
                'workspace_homologated': self.identity_confirmed, 'protocol': VERSION,
                'community_persisted': False, 'retries': 0, 'fallbacks': 0}
