"""Read-only homologation boundary. No prepare, reserve, start or stop dispatch."""
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
import ntpath
import time
from types import MappingProxyType

from .batch_manifest import fingerprint, exact
from .batch_safety import execution_gate
from .tester import payload, BacktestConfig


class Operation(str,Enum):
    QUERY='query'
    OFFLINE_PREPARATION='offline_preparation'
    RESERVATION='operational_reservation'
    START='backtest_start'
    MONITOR='monitor'
    STOP='stop_request'
    RECONCILIATION='read_only_reconciliation'


class HomologationTransport:
    """Injected bounded transport, separate preflight per server, no retries.

    Elapsed-time enforcement is cooperative. A blocked synchronous dependency
    must have its own deadline (RicoQueryMCP inherits the HTTP timeout). A late
    response is recorded as failure, never interpreted as a successful command.
    """
    live_execution_enabled=False
    TOOLS=MappingProxyType({'metaeditor':frozenset({'get_workspace_info'}),
           'terminal':frozenset({'get_workspace_info','tester_get_status','get_trading_account_info','get_marketwatch_symbols'})})

    def __init__(self,call_tool,*,timeout_seconds=15,clock=time.monotonic):
        if type(timeout_seconds) not in (int,float) or not 0<timeout_seconds<=60:
            raise ValueError('bounded timeout required')
        self._call_tool=call_tool;self.timeout=timeout_seconds;self.clock=clock
        self._preflight=set();self._audit=[];self.blocked=False

    @property
    def audit(self):return deepcopy(self._audit)

    def query(self,server,name,arguments):
        if server not in self.TOOLS or name not in self.TOOLS[server]:
            raise PermissionError('tool forbidden by read-only homologation contract')
        if name=='get_workspace_info' or name=='get_trading_account_info':
            exact(arguments,set(),'query')
        elif name=='tester_get_status':
            exact(arguments,{'run_id'},'tester status')
            if not isinstance(arguments['run_id'],str) or not arguments['run_id']:
                raise ValueError('known historical run_id required; never reserve one for a query')
        else:
            if not isinstance(arguments,dict) or set(arguments)-{'symbol','limit','include_hidden'}:
                raise ValueError('invalid symbol query')
            if 'symbol' in arguments and (not isinstance(arguments['symbol'],str) or not arguments['symbol']):
                raise ValueError('invalid symbol filter')
            if 'limit' in arguments and (type(arguments['limit']) is not int or not 1<=arguments['limit']<=1000):
                raise ValueError('invalid query limit')
            if 'include_hidden' in arguments and type(arguments['include_hidden']) is not bool:
                raise ValueError('invalid query flag')
        if name!='get_workspace_info' and server not in self._preflight:
            raise PermissionError('get_workspace_info must succeed first for each server')
        start=self.clock()
        entry=dict(sequence=len(self._audit)+1,server=server,tool=name,arguments_sha256=fingerprint(arguments),
                   observed_at=datetime.now(timezone.utc).isoformat(),operation=Operation.QUERY.value)
        try:
            result=payload(self._call_tool(server,name,deepcopy(arguments)))
            if self.clock()-start>=self.timeout:raise TimeoutError('query response exceeded deadline')
            if not isinstance(result,dict):raise ValueError('query response must be an object')
            if name=='get_workspace_info' and not isinstance(result.get('workspace',{}).get('mql5_folder'),str):
                raise ValueError('workspace identity missing')
            if name=='tester_get_status' and result.get('tester_status',result.get('status')) not in ('stopped','started','running'):
                raise ValueError('unknown tester state')
            entry.update(outcome='observed',response_sha256=fingerprint(result))
            if name=='get_workspace_info':self._preflight.add(server)
            return deepcopy(result)
        except BaseException as exc:
            self.blocked=True
            self._preflight.discard(server)
            entry.update(outcome='failed',error_type=type(exc).__name__)
            raise
        finally:
            entry['elapsed_seconds']=self.clock()-start
            self._audit.append(entry)  # No raw response, headers or exception message.

    def prepare_offline(self,config):
        if type(config) is not BacktestConfig:raise ValueError('validated BacktestConfig required')
        return dict(operation=Operation.OFFLINE_PREPARATION.value,simulation_only=True,
                    arguments=config.prepare_arguments('<OFFLINE_MQL5>\\Profiles\\Tester\\proposal.ini'),
                    live_execution_enabled=False)

    def monitor(self,run_id):return self.query('terminal','tester_get_status',{'run_id':run_id})

    def reconcile(self,run_id):
        return dict(operation=Operation.RECONCILIATION.value,observation=self.monitor(run_id),
                    locks_released=False,attempts_changed=False,live_execution_enabled=False)

    def reserve(self,*args,**kwargs):execution_gate()
    def start(self,*args,**kwargs):execution_gate()
    def stop(self,*args,**kwargs):execution_gate()


def assess_probe_observations(metaeditor,terminal,account,tester,agents,concurrency,*,expected_mql5,expected_build):
    """Assess a point-in-time read-only snapshot; never grant execution readiness."""
    def folder(document):
        path=document.get('workspace',{}).get('mql5_folder')
        return ntpath.normcase(ntpath.normpath(path)) if isinstance(path,str) else None
    expected=ntpath.normcase(ntpath.normpath(expected_mql5))
    terminal_info=account.get('terminal',{})
    identity=account.get('account',{})
    checks=dict(shared_expected_mql5=folder(metaeditor)==folder(terminal)==expected,
        builds_match=all(type(v) is int and v==expected_build for v in (
            metaeditor.get('compiler',{}).get('compiler_mql5_build'),terminal.get('compiler',{}).get('compiler_mql5_build'),terminal_info.get('build'))),
        rico_demo=identity.get('server')=='Rico-DEMO' and identity.get('type')=='demo' and terminal_info.get('program_name')=='Rico - MetaTrader 5',
        connected=terminal_info.get('server_connected') is True,
        tester_stopped=tester.get('tester_status',tester.get('status'))=='stopped',
        local_agents_only=agents.get('use_local') is True and agents.get('use_remote') is False and agents.get('use_cloud') is False and agents.get('visible_status')=='ready',
        no_concurrency_observed=all(type(concurrency.get(k)) is int and concurrency[k]==0 for k in ('metatester_processes','project_locks','shared_terminal_locks')))
    return dict(checks=checks,query_homologation_ready=all(checks.values()),live_execution_enabled=False,
                exclusive_future_window_reserved=False,scope='point_in_time_read_only_observation')
