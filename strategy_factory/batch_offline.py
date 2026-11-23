"""Safe batch dry-run CLI. No MCP, transport injection or real execution path."""
import argparse
from contextlib import closing
import json
import sqlite3
from pathlib import Path

from .analysis import read_artifact, write_artifact
from .batch_control import BatchController, BatchBlocked
from .batch_manifest import fingerprint
from .batch_safety import validate_plan, execution_gate, check_planning_authorization
from .batch_consolidation import consolidate


class OfflineBatchController(BatchController):
    """Reuse durable simulation, budgets, locks and summary 1.1 generation.

    A separate root prevents accidental reuse of historical planning ledgers.
    The complete envelope is pinned alongside the legacy manifest snapshot.
    """
    def plan(self,document):
        plan=validate_plan(document)
        manifest=plan['manifest']
        with self._worker(manifest['batch_id']):
            state=self._plan(manifest)
            path=self.root/manifest['batch_id']/'safe_plan.json'
            if path.exists():
                if fingerprint(read_artifact(path))!=fingerprint(plan):
                    raise BatchBlocked('safe plan changed; use a new batch ID')
            else:
                self._write(manifest,Path('safe_plan.json'),plan)
            with self._db() as db:
                db.execute('INSERT OR IGNORE INTO safe_plans VALUES(?,?)',
                           (manifest['batch_id'],fingerprint(plan)))
            return state

    def _load(self,db,batch_id,*,verify_snapshot=True):
        manifest,state=super()._load(db,batch_id,verify_snapshot=verify_snapshot)
        path=self.root/batch_id/'safe_plan.json'
        if not path.exists():
            raise BatchBlocked('safe plan missing; incomplete preparation')
        plan=validate_plan(read_artifact(path))
        if fingerprint(plan['manifest'])!=fingerprint(manifest):
            raise BatchBlocked('safe plan manifest mismatch')
        stored=db.execute('SELECT digest FROM safe_plans WHERE id=?',(batch_id,)).fetchone()
        if stored is None or stored[0]!=fingerprint(plan):
            raise BatchBlocked('safe plan envelope changed')
        return manifest,state

    def __init__(self,root,**kwargs):
        database=Path(root)/'control.sqlite'
        if database.exists():
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='safe_plans'").fetchone():
                    raise BatchBlocked('historical ledger cannot be migrated; choose a separate dry-run root')
        super().__init__(root,**kwargs)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS safe_plans (id TEXT PRIMARY KEY, digest TEXT NOT NULL)')

    def execute(self,*args,**kwargs):
        execution_gate()

    def authorization(self,*args,**kwargs):
        raise PermissionError('phase 3.3A does not issue authorization records')

    def check_authorization(self,batch_id,record,*,run_id,attempt,now=None):
        with self._db() as db:
            _,state=self._load(db,batch_id)
            if state['cancel_requested'] or state['status'] in ('simulating','cancel_requested','simulated'):
                raise PermissionError('batch state forbids planning authorization use')
            plan=read_artifact(self.root/batch_id/'safe_plan.json')
            consumed={(key,a['attempt']) for key,run in state['runs'].items() for a in run['attempts']}
            return check_planning_authorization(plan,record,run_id=run_id,attempt=attempt,
                                                consumed=consumed,now=now)

    def _write(self,manifest,relative,value,run_directory=None):
        if Path(relative).name=='run_summary.json':
            plan=validate_plan(read_artifact(self.root/manifest['batch_id']/'safe_plan.json'))
            context=value['batch_context']
            run_id=Path(relative).parts[1]
            scenario=next(s for s in plan['scenarios'] if s['run_id']==run_id)
            context.update(plan_sha256=fingerprint(plan),scenario_sha256=scenario['scenario_sha256'],
                           stage=scenario['stage'],history_status=plan['periods'][scenario['stage']]['history_status'])
        return super()._write(manifest,relative,value,run_directory)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for command in ('validate','dry-run'):
        sub=commands.add_parser(command)
        sub.add_argument('plan',type=Path)
        if command=='dry-run':
            sub.add_argument('--root',type=Path,required=True)
            sub.add_argument('--outcomes',type=Path)
    sub=commands.add_parser('consolidate')
    sub.add_argument('summaries',nargs='+',type=Path)
    sub.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='consolidate':
        write_artifact(args.output,consolidate(read_artifact(p) for p in args.summaries))
        return
    plan=validate_plan(read_artifact(args.plan))
    if args.command=='validate':
        result=dict(valid=True,plan_sha256=fingerprint(plan),execution_enabled=False)
    else:
        controller=OfflineBatchController(args.root)
        controller.plan(plan)
        result=controller.simulate(plan['manifest']['batch_id'],
                   outcomes=read_artifact(args.outcomes) if args.outcomes else None)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    main()
