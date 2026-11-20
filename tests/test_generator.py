"""Offline generator contracts and synthetic rule cases; no compiler/tester API."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import summarize_run,read_artifact
from strategy_factory.batch_manifest import validate_manifest
from strategy_factory.generator import (render,validate_spec,generate_many,verify_candidate,
    manifest_strategy,attach_candidate,DuplicateCandidate,audit_candidate)

ROOT=Path(__file__).resolve().parents[1]
SPECS=read_artifact(ROOT/'config/generator/demo_specs.json')


class GeneratorTests(unittest.TestCase):
    def test_three_distinct_demo_candidates(self):
        results=[render(spec) for spec in SPECS]
        self.assertEqual(len({m['candidate_id'] for _,_,m in results}),3)
        self.assertEqual(len({m['source_sha256'] for _,_,m in results}),3)

    def test_committed_demo_artifacts_and_manifest_match_generator(self):
        manifest=validate_manifest(read_artifact(ROOT/'config/generator/demo_manifest.json'))
        entries={s['strategy_id']:s for s in manifest['strategies']}
        for spec in SPECS:
            expected=render(spec)[2]
            root=ROOT/'MQL5/Experts/MT5StrategyFactory/Generated'/expected['candidate_id']
            self.assertEqual(verify_candidate(root),expected)
            self.assertEqual(entries[expected['candidate_id']]['ea']['source_sha256'],expected['source_sha256'])
            self.assertEqual(len(entries[expected['candidate_id']]['ea']['compiled_sha256']),64)
        self.assertEqual(len(manifest['runs']),3)
        self.assertFalse(manifest['policy']['allow_live_trading'])

    def test_deterministic_across_key_and_and_rule_order(self):
        original=SPECS[2]
        reordered=dict(reversed(list(original.items())))
        reordered=deepcopy(reordered)
        reordered['entries']['long'].reverse()
        self.assertEqual(render(original),render(reordered))

    def test_equivalent_numeric_representation_is_canonical(self):
        changed=deepcopy(SPECS[0]);changed['risk']['sl_percent']=1.0
        self.assertEqual(render(changed),render(SPECS[0]))

    def test_changes_create_different_identity_and_source_hash(self):
        changed=deepcopy(SPECS[0]);changed['risk']['tp_percent']=3
        a,b=render(changed)[2],render(SPECS[0])[2]
        self.assertNotEqual(a['candidate_id'],b['candidate_id'])
        self.assertNotEqual(a['source_sha256'],b['source_sha256'])

    def test_unknown_code_fields_and_injection_are_rejected(self):
        variants=[]
        doc=deepcopy(SPECS[0]);doc['code']='OrderSend(request,result)';variants.append(doc)
        doc=deepcopy(SPECS[0]);doc['symbol']='PETR4"; OrderSend(x,y);';variants.append(doc)
        doc=deepcopy(SPECS[0]);doc['entries']['long'][0]['method']='EMA); OrderSend(x,y)';variants.append(doc)
        doc=deepcopy(SPECS[0]);doc['entries']['long'][0]['kind']='arbitrary_code';variants.append(doc)
        for spec in variants:
            with self.assertRaises(ValueError):validate_spec(spec)

    def test_bounds_risk_and_parameter_types(self):
        for key,value in (('sl_percent',0),('sl_percent',float('nan')),('tp_percent',51),
                          ('sl_percent',0.123456789),('max_entries',True),('max_holding_bars',0),
                          ('deviation_points',101),('max_spread_points',-1),('volume_mode','martingale')):
            spec=deepcopy(SPECS[0]);spec['risk'][key]=value
            with self.assertRaises(ValueError):validate_spec(spec)
        spec=deepcopy(SPECS[0]);spec['entries']['long'][0]['fast']=21
        with self.assertRaises(ValueError):validate_spec(spec)

    def test_inactive_and_identical_sides_are_rejected(self):
        spec=deepcopy(SPECS[0]);spec['entries']['short']=deepcopy(spec['entries']['long'])
        with self.assertRaises(ValueError):validate_spec(spec)
        spec=deepcopy(SPECS[0]);spec['exits']['short']=deepcopy(spec['exits']['long'])
        with self.assertRaises(ValueError):validate_spec(spec)
        spec=deepcopy(SPECS[0]);spec['entries']={'long':[],'short':[]}
        with self.assertRaises(ValueError):validate_spec(spec)

    def test_contradictory_ma_and_rsi_and_adx_clauses(self):
        variants=[]
        spec=deepcopy(SPECS[0]);opposite=deepcopy(spec['entries']['long'][0]);opposite['direction']='below';spec['entries']['long'].append(opposite);variants.append(spec)
        spec=deepcopy(SPECS[1]);spec['entries']['long']=[
            dict(kind='rsi_level',period=14,level=70,relation='above'),
            dict(kind='rsi_level',period=14,level=30,relation='below')];variants.append(spec)
        spec=deepcopy(SPECS[1]);spec['entries']['long']=[
            dict(kind='rsi_cross',period=14,level=30,relation='above'),
            dict(kind='rsi_cross',period=14,level=70,relation='below')];variants.append(spec)
        spec=deepcopy(SPECS[1]);spec['entries']['long']=[
            dict(kind='adx_strength',period=14,minimum=50,maximum=60),
            dict(kind='adx_direction',period=14,minimum=70,direction='up')];variants.append(spec)
        for spec in variants:
            with self.assertRaises(ValueError):validate_spec(spec)

    def test_duplicate_rules_and_limits(self):
        spec=deepcopy(SPECS[0]);spec['entries']['long'].append(deepcopy(spec['entries']['long'][0]))
        with self.assertRaises(ValueError):validate_spec(spec)
        spec=deepcopy(SPECS[0]);spec['entries']['long']=[dict(kind='price_ma',period=p,method='EMA',relation='above') for p in range(2,8)]
        with self.assertRaises(ValueError):validate_spec(spec)
        spec=deepcopy(SPECS[0])
        for offset,(group,side) in enumerate((('entries','long'),('entries','short'),('exits','long'),('exits','short'))):
            spec[group][side]=[dict(kind='price_ma',period=p,method='EMA',relation='above' if offset%2==0 else 'below')
                               for p in range(2+offset*5,7+offset*5)]
        with self.assertRaises(ValueError):validate_spec(spec)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):generate_many(SPECS,output_root=folder,limit=2)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_validation_before_any_candidate_or_registry_write(self):
        invalid=deepcopy(SPECS[0]);invalid['risk']['max_entries']=0
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):
                generate_many([SPECS[0],invalid],output_root=root/'out',registry=root/'registry.sqlite')
            self.assertEqual(list(root.iterdir()),[])

    def test_registry_duplicates_block_reordered_semantic_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            records=generate_many(SPECS,output_root=root/'out',registry=root/'registry.sqlite',limit=3)
            reordered=deepcopy(SPECS[0]);reordered['entries']['long'].reverse()
            with self.assertRaises(DuplicateCandidate):
                generate_many([reordered],output_root=root/'other',registry=root/'registry.sqlite')
            self.assertFalse((root/'other').exists())
            self.assertEqual(verify_candidate(root/'out'/records[0]['candidate_id']),records[0])

    def test_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            metadata=generate_many([SPECS[0]],output_root=root/'out',registry=root/'registry.sqlite')[0]
            path=root/'out'/metadata['candidate_id']/metadata['source_file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),metadata['source_sha256'])
            self.assertNotIn(b'\r\n',path.read_bytes())
            self.assertTrue(audit_candidate(path.parent)['static_check_passed'])
            path.write_bytes(path.read_bytes()+b'// SYNTHETIC alteration\n')
            with self.assertRaises(ValueError):verify_candidate(path.parent)
            with self.assertRaises(DuplicateCandidate):
                generate_many([SPECS[0]],output_root=root/'out',registry=root/'registry.sqlite')
            self.assertTrue(path.read_bytes().endswith(b'SYNTHETIC alteration\n'))

    def test_failed_creation_keeps_history_and_partial_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry=root/'registry.sqlite'
            with patch('strategy_factory.generator.write_artifact',side_effect=OSError('SYNTHETIC failure')):
                with self.assertRaises(OSError):generate_many([SPECS[0]],output_root=root/'out',registry=registry)
            with sqlite3.connect(registry) as db:
                self.assertEqual(db.execute('SELECT status FROM candidates').fetchone()[0],'failed:OSError')
            db.close()
            with self.assertRaises(DuplicateCandidate):
                generate_many([SPECS[0]],output_root=root/'out',registry=registry)

    def test_closed_bars_and_correct_cross_buffer_indices(self):
        source=render(SPECS[0])[1]
        self.assertIn('CopyBuffer(handle,buffer,1,2,values)',source)
        self.assertIn('CopyClose(_Symbol,_Period,1,2,close)',source)
        self.assertIn('[0]<=',source)
        self.assertIn('[1]>',source)
        self.assertNotIn('CopyBuffer(handle,buffer,0',source)

    def test_each_trade_sender_has_tester_guard_and_cleanup_cannot_trade(self):
        for spec in SPECS:
            source=render(spec)[1]
            init=source.split('int OnInit()')[1].split('bool ClosedBuffer')[0]
            enter=source.split('void Enter(')[1].split('void OnTick()')[0]
            close=source.split('bool CloseOwned(')[1].split('void Enter(')[0]
            cleanup=source.split('void OnDeinit(')[1].split('double OnTester()')[0]
            self.assertLess(init.index('if(!TesterOnly())'),init.index('g_trade.SetExpertMagicNumber'))
            self.assertLess(enter.index('if(!TesterOnly()'),enter.index('g_trade.Buy('))
            self.assertLess(close.index('if(!TesterOnly()'),close.index('g_trade.PositionClose('))
            self.assertNotIn('g_trade.',cleanup)
            self.assertIn('!MQLInfoInteger(MQL_OPTIMIZATION)',source)
            self.assertIn('SYMBOL_VOLUME_MIN',source)
            self.assertNotIn('input ',source)

    def test_no_grid_progression_or_external_dependencies(self):
        for spec in SPECS:
            source=render(spec)[1]
            self.assertEqual(source.count('g_trade.Buy('),1)
            self.assertEqual(source.count('g_trade.Sell('),1)
            self.assertNotIn('OrderSend(',source)
            self.assertNotIn('WebRequest(',source)
            self.assertNotIn('#import',source)
            self.assertIn('if(enter_long==enter_short) return;',source)
            self.assertIn('entry not fully confirmed; no retries',source)

    def test_sma_and_null_spread_are_supported(self):
        spec=deepcopy(SPECS[0]);spec['entries']['long'][0]['method']='SMA';spec['risk']['max_spread_points']=None
        source=render(spec)[1]
        self.assertIn('MODE_SMA',source)
        self.assertIn('MAX_SPREAD_POINTS=-1.0',source)

    def test_batch_manifest_and_summary_integration_preserve_unknowns(self):
        spec,_,metadata=render(SPECS[0])
        compiled='C:\\SYNTHETIC\\'+metadata['source_file'].replace('.mq5','.ex5')
        strategy=manifest_strategy(metadata,compiled)
        manifest=read_artifact(ROOT/'config/batches/example.json')
        manifest['strategies']=[strategy]
        manifest['runs']=manifest['runs'][:1]
        manifest['runs'][0].update(strategy_id=metadata['candidate_id'],inputs={})
        self.assertEqual(validate_manifest(manifest)['strategies'][0]['ea']['source_sha256'],metadata['source_sha256'])
        summary=summarize_run(None,parameters=dict(manifest['runs'][0]['parameters'],expert=compiled),
            local_run_id='synthetic-generated',inputs={},execution={'status':'simulated'})
        attached=attach_candidate(summary,metadata)
        self.assertEqual(attached['candidate_context']['candidate_id'],metadata['candidate_id'])
        self.assertNotIn('candidate_context',summary)
        self.assertIsNone(attached['metrics']['net_profit']['value'])
        self.assertIsNone(strategy['ea']['compiled_sha256'])
