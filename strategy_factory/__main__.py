"""CLI defaults to offline simulation; live tester requires two explicit flags."""
import argparse
import json
from pathlib import Path

from .mcp import RicoMCP
from .tester import BacktestConfig, TesterRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path, help='JSON BacktestConfig')
    parser.add_argument('--state-root', type=Path, default=Path('runs'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--authorize-backtest', action='store_true')
    parser.add_argument('--endpoint', default='http://127.0.0.1:22346/mcp')
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    config = BacktestConfig(**json.loads(args.config.read_text(encoding='utf-8-sig')))
    if args.execute and not args.authorize_backtest:
        parser.error('--execute requires --authorize-backtest after human authorization')
    client = RicoMCP(args.endpoint) if args.execute else None
    result = TesterRunner(args.state_root, client).run(config, simulate=not args.execute,
                            authorized=args.authorize_backtest, timeout=args.timeout)
    print(result)


if __name__ == '__main__':
    main()
