"""Batch planning and simulation CLI. No command can execute live backtests."""
import argparse
import json
from pathlib import Path

from .analysis import read_artifact,write_artifact
from .batch_manifest import validate_manifest,fingerprint,approval_phrase,manifest_schema
from .batch_control import BatchController


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('runs/batches'))
    commands=parser.add_subparsers(dest='command',required=True)
    schema=commands.add_parser('schema')
    schema.add_argument('--output',required=True,type=Path)
    for name in ('validate','plan','propose-authorization','simulate'):
        sub=commands.add_parser(name)
        sub.add_argument('manifest',type=Path)
        if name=='simulate':
            sub.add_argument('--resume-plan',type=Path)
            sub.add_argument('--cancel-after',type=int)
    for name in ('status','cancel','recover','resume-plan'):
        sub=commands.add_parser(name)
        sub.add_argument('batch_id')
        if name=='resume-plan':
            sub.add_argument('--attempt',action='append',required=True,help='RUN_ID:ATTEMPT')
            sub.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='schema':
        write_artifact(args.output,manifest_schema())
        return
    if hasattr(args,'manifest'):
        manifest=validate_manifest(read_artifact(args.manifest))
        if args.command=='validate':
            print(json.dumps({'valid':True,'manifest_sha256':fingerprint(manifest),'live_execution_enabled':False}))
            return
        if args.command=='propose-authorization':
            print(json.dumps({'proposal_only':True,'approval_phrase':approval_phrase(manifest),
                'manifest_sha256':fingerprint(manifest),'budget':manifest['budget'],'live_execution_enabled':False},ensure_ascii=False))
            return
    controller=BatchController(args.root)
    if args.command in ('plan','simulate'):
        result=controller.plan(manifest)
        if args.command=='simulate':
            result=controller.simulate(manifest['batch_id'],cancel_after=args.cancel_after,
                       resume=read_artifact(args.resume_plan) if args.resume_plan else None)
    elif args.command=='status':
        result=controller.status(args.batch_id)
    elif args.command=='cancel':
        result=controller.cancel(args.batch_id)
    elif args.command=='recover':
        result=controller.recover_interrupted(args.batch_id)
    else:
        selected={}
        for value in args.attempt:
            run,separator,attempt=value.partition(':')
            if not separator or run in selected:
                raise ValueError('invalid or duplicate resume selection')
            selected[run]=int(attempt)
        result=controller.resume_plan(args.batch_id,selected)
        write_artifact(args.output,result)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    main()
