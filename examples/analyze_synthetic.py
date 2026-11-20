"""Create two explicitly SYNTHETIC summaries and compare them, without MT5."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy_factory.analysis import compare_runs, summarize_run, write_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'runs'/'synthetic_phase24')
    args = parser.parse_args()
    # A dedicated new directory protects previous examples and real evidence.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    first = json.loads((ROOT/'tests/fixtures/financial_synthetic.json').read_text(encoding='utf-8'))
    second = deepcopy(first)
    second['run_id'] = 'synthetic-financial-variant'
    second['statistics'].update(net_profit=-50, final_balance=9950, gross_profit=150,
        gross_loss=-200, profit_factor=0.75, winning_trades=1, losing_trades=3,
        win_rate=25, expected_payoff=-12.5)
    second['period_results'] = [{'period':'synthetic-period','net_profit':-50,'trades':4,'win_rate':25}]
    parameters = dict(expert='SYNTHETIC.ex5',symbol='PETR4',timeframe='M5',
        from_date='2026-11-03',to_date='2026-11-14',model='every tick',
        deposit=10000,currency='BRL',leverage=1,execution_delay=0)
    context = dict(terminal_build=6230,agents='local_only',
        history_fingerprint=hashlib.sha256(b'SYNTHETIC history').hexdigest(),
        costs_fingerprint=hashlib.sha256(b'SYNTHETIC costs').hexdigest())
    summaries = []
    for index, report in enumerate((first,second),1):
        summary = summarize_run(report,parameters=parameters,
            run_id=report['run_id'],inputs={'InpFastPeriod':9 if index==1 else 5,'InpSlowPeriod':21},
            execution={'status':'completed'},data_context=context,synthetic=True,
            native_reference=deepcopy(report),reference_run_id=report['run_id'])
        write_artifact(args.output_dir/f'synthetic_summary_{index}.json',summary)
        summaries.append(summary)
    write_artifact(args.output_dir/'synthetic_comparison.json',compare_runs(summaries))
    print(args.output_dir)


if __name__ == '__main__':
    main()
