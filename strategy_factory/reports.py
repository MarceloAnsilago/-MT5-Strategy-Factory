"""Conservative extraction of explicit MT5 HTML / normalized JSON statistics."""
import json
import math
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower())
                   if not unicodedata.combining(c)).strip().rstrip(':')


ALIASES = {
    'net_profit': ('total net profit', 'lucro liquido total', 'lucro liquido'),
    'profit_factor': ('profit factor', 'fator de lucro'),
    'balance_drawdown_absolute': ('balance drawdown absolute', 'rebaixamento absoluto do saldo'),
    'balance_drawdown_relative': ('balance drawdown relative', 'rebaixamento relativo do saldo'),
    'equity_drawdown_absolute': ('equity drawdown absolute', 'rebaixamento absoluto do capital liquido'),
    'equity_drawdown_relative': ('equity drawdown relative', 'rebaixamento relativo do capital liquido'),
    'trades': ('total trades', 'total de negociacoes'),
    'win_rate': ('profit trades (% of total)', 'negociacoes com lucro (% do total)'),
    'expected_payoff': ('expected payoff', 'retorno esperado'),
}


class TableCells(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell = None
        if tag == 'tr':
            self.rows.append(self.row)


def number(value):
    text = str(value).replace('\u00a0', '').replace(' ', '')
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)*', text):
        raise ValueError('unavailable numeric value')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    result = float(text)
    if not math.isfinite(result):
        raise ValueError('non-finite value')
    return result


def analyze_report(source):
    """Absent/ambiguous statistics stay None; never infer wins from deals."""
    raw = source
    if isinstance(source, Path):
        data = source.read_bytes()
        raw = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    if isinstance(raw, str) and raw.lstrip().startswith('{'):
        raw = json.loads(raw)
    found = {}
    if isinstance(raw, dict):
        # Rico's native backtest JSON uses profit for total test profit.
        # Require its identifying fields; do not reinterpret arbitrary profit objects.
        if all(key in raw for key in ('run_id', 'generated_bars', 'generated_ticks', 'initial_deposit', 'profit', 'trades')) and 'statistics' not in raw:
            raw = dict(raw)
            raw.setdefault('net_profit', raw['profit'])
        stats = raw.get('statistics', raw)
        if isinstance(stats, dict):
            found = {k: [v] for k, v in stats.items() if k in ALIASES and v is not None}
    elif isinstance(raw, str):
        parser = TableCells()
        parser.feed(raw)
        for row in parser.rows:
            for i, cell in enumerate(row[:-1]):
                for key, labels in ALIASES.items():
                    if normalized(cell) in labels:
                        found.setdefault(key, []).append(row[i + 1])
    metrics, issues = {}, []
    for key in ALIASES:
        values = found.get(key, [])
        try:
            if len(values) != 1 or isinstance(values[0], bool):
                raise ValueError('missing or duplicate')
            value = values[0]
            if key in ('win_rate', 'balance_drawdown_relative', 'equity_drawdown_relative'):
                # win_rate normalized JSON is percent; HTML wins contain count (percent).
                match = re.search(r'([\d.,]+)\s*%', str(value))
                value = number(match.group(1)) if match else number(value)
                if not 0 <= value <= 100:
                    raise ValueError('invalid percentage')
            else:
                value = number(value)
            if key == 'trades' and (value < 0 or not value.is_integer()):
                raise ValueError('invalid trade count')
            metrics[key] = int(value) if key == 'trades' else value
        except (ValueError, TypeError):
            metrics[key] = None
            issues.append(key + ': indisponivel ou inconclusivo')
    periods = None
    # Accept explicitly aggregated periods in the normalized JSON contract only.
    if isinstance(raw, dict) and isinstance(raw.get('period_results'), list):
        periods = []
        seen = set()
        for entry in raw['period_results']:
            try:
                period = entry['period']
                if not isinstance(period, str) or not period or period in seen:
                    raise ValueError('invalid/duplicate period')
                seen.add(period)
                item = {'period': period}
                for key in ('net_profit', 'trades', 'win_rate'):
                    value = entry.get(key)
                    if value is None:
                        item[key] = None
                        continue
                    value = number(value)
                    if key == 'trades' and (value < 0 or not value.is_integer()):
                        raise ValueError('invalid trade count')
                    if key == 'win_rate' and not 0 <= value <= 100:
                        raise ValueError('invalid percentage')
                    item[key] = int(value) if key == 'trades' else value
                periods.append(item)
            except (KeyError, TypeError, ValueError):
                periods = None
                break
        if not periods:
            periods = None
    if periods is None:
        issues.append('period_results: indisponivel; requer historico atribuido por periodo')
    return {'status': 'complete' if not issues else 'inconclusive', 'metrics': metrics,
            'period_results': periods, 'issues': issues}
