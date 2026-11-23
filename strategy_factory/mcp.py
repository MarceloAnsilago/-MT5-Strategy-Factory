"""Small synchronous Streamable HTTP client; bearer credential stays in memory."""
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('MCP redirects are forbidden')


class RicoMCP:
    ALLOWED = frozenset(('get_workspace_info', 'tester_prepare_config',
                         'tester_run_backtest', 'tester_get_status',
                         'tester_get_report', 'tester_stop'))

    def __init__(self, endpoint, *, token_env='MT5_TERMINAL_TOKEN', request_timeout=15):
        parsed = urlparse(endpoint)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('MCP requires a credential-free loopback HTTP URL')
        if not 0 < request_timeout <= 60:
            raise ValueError('request timeout must be between 0 and 60 seconds')
        self.endpoint, self.timeout = endpoint, request_timeout
        self._token = os.environ[token_env]
        if not self._token or '\r' in self._token or '\n' in self._token:
            raise ValueError('invalid bearer token')
        self._session = None
        self._id = 0
        self._opener = build_opener(ProxyHandler({}), NoRedirect())
        result = self._rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                            'clientInfo': {'name': 'mt5-strategy-factory', 'version': '0.1'}})
        self._protocol = result['protocolVersion']
        self._rpc('notifications/initialized', {}, notification=True)

    def _rpc(self, method, params, notification=False):
        self._id += 1
        request_id = self._id
        body = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            body['id'] = request_id
        headers = {'Authorization': 'Bearer ' + self._token,
                   'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self._session:
            headers['Mcp-Session-Id'] = self._session
        if hasattr(self, '_protocol'):
            headers['MCP-Protocol-Version'] = self._protocol
        request = Request(self.endpoint, json.dumps(body).encode(), headers)
        with self._opener.open(request, timeout=self.timeout) as response:
            session = response.headers.get('Mcp-Session-Id')
            if session:
                self._session = session
            if notification:
                return None
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                event = []
                for raw_line in response:
                    line = raw_line.decode('utf-8').rstrip('\r\n')
                    if line.startswith('data:'):
                        event.append(line[5:].lstrip())
                    elif not line and event:
                        message = json.loads('\n'.join(event))
                        event = []
                        if message.get('id') == request_id:
                            break
                else:
                    raise RuntimeError('MCP stream ended without response')
            else:
                message = json.load(response)
        if message.get('id') != request_id or 'error' in message:
            raise RuntimeError('MCP protocol error; remote details omitted')
        return message['result']

    def __call__(self, name, arguments):
        if name not in self.ALLOWED:
            raise PermissionError('tool outside tester allowlist')
        return self._rpc('tools/call', {'name': name, 'arguments': arguments})


class RicoQueryMCP(RicoMCP):
    """Read-only client variant; configuration cannot add operational tools."""
    ALLOWED = frozenset(('get_workspace_info','tester_get_status',
                         'get_trading_account_info','get_marketwatch_symbols'))
