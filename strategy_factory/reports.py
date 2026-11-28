"""Conservative extraction of explicit MT5 HTML / normalized JSON statistics."""
import json
import math
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower())
                   if not unicodedata.combining(c)).strip().rstrip(':').rstrip()


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
    'initial_balance': ('initial deposit', 'deposito inicial'),
    'final_balance': ('final balance', 'saldo final'),
    'gross_profit': ('gross profit', 'lucro bruto'),
    'gross_loss': ('gross loss', 'perda bruta'),
    'deals': ('total deals', 'ofertas total', 'total de negocios'),
    'orders': ('total orders', 'total de ordens'),
    'positions': ('total positions', 'total de posicoes'),
    'winning_trades': ('profit trades (% of total)', 'negociacoes com lucro (% do total)', 'negociacoes com lucro (% of total)'),
    'losing_trades': ('loss trades (% of total)', 'negociacoes com perda (% do total)', 'negociacoes com perda (% of total)'),
    'history_quality': ('history quality', 'qualidade do historico'),
}
ALIASES['win_rate'] += ('negociacoes com lucro (% of total)',)
COUNT_METRICS = frozenset(('trades', 'deals', 'orders', 'positions', 'winning_trades', 'losing_trades'))


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
    native_mapping = {}
    derived_metrics = {}
    if isinstance(raw, dict):
        # Rico's native backtest JSON uses profit for total test profit.
        # Require its identifying fields; do not reinterpret arbitrary profit objects.
        if all(key in raw for key in ('run_id', 'generated_bars', 'generated_ticks', 'initial_deposit', 'profit', 'trades')) and 'statistics' not in raw:
            raw = dict(raw)
            original = dict(raw)
            # Conflicting aliases must not silently prefer one value.
            if 'net_profit' in raw and raw['net_profit'] != raw['profit']:
                raw['net_profit'] = None
            else:
                raw['net_profit'] = raw['profit']
            if 'initial_balance' in raw and raw['initial_balance'] != raw['initial_deposit']:
                raw['initial_balance'] = None
            else:
                raw['initial_balance'] = raw['initial_deposit']
            # The Rico JSON reports gross_loss as a positive magnitude, unlike
            # TesterStatistics/normalized JSON where losing money is negative.
            if 'gross_loss' in raw:
                try:
                    value = -abs(number(raw['gross_loss']))
                    raw['gross_loss'] = value
                    native_mapping['gross_loss'] = {'field':'gross_loss','raw':str(original['gross_loss']),
                                                   'operation':'negative magnitude','value':value}
                except (ValueError, TypeError):
                    pass
            for target,field in (('winning_trades','profit_trades'),('losing_trades','loss_trades'),
                    ('balance_drawdown_relative','rel_drawdown_percent_balance'),
                    ('equity_drawdown_relative','rel_drawdown_percent_equity')):
                if field in raw:
                    raw[target] = raw[field] if target not in raw or raw[target]==raw[field] else None
                    native_mapping[target] = {'field':field,'raw':str(original[field])}
            # These are explicit calculations, kept separate from reported metrics.
            for target,field in (('balance_drawdown_absolute','balance_min'),('equity_drawdown_absolute','equity_min')):
                try:
                    initial,minimum = number(original['initial_deposit']),number(original[field])
                    if initial<0 or max(abs(initial),abs(minimum))>=1e100:
                        raise ValueError('invalid native balance')
                    derived_metrics[target] = {'value':max(0,initial-minimum),
                       'formula':'max(0, initial_deposit - '+field+')',
                       'operands':{'initial_deposit':initial,field:minimum}}
                except (KeyError,ValueError,TypeError):
                    pass
            try:
                wins,trades = number(original['profit_trades']),number(original['trades'])
                if not (wins.is_integer() and trades.is_integer() and 0<=wins<=trades and trades>0):
                    raise ValueError('invalid trade counts')
                derived_metrics['win_rate'] = {'value':100*wins/trades,
                    'formula':'100 * profit_trades / trades',
                    'operands':{'profit_trades':int(wins),'trades':int(trades)}}
            except (KeyError,ValueError,TypeError):
                pass
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
    metrics, issues, availability = {}, [], {}
    for key in ALIASES:
        values = found.get(key, [])
        try:
            if len(values) != 1 or isinstance(values[0], bool):
                raise ValueError('missing or duplicate')
            value = values[0]
            if key in ('win_rate', 'balance_drawdown_relative', 'equity_drawdown_relative', 'history_quality'):
                # win_rate normalized JSON is percent; HTML wins contain count (percent).
                matches = re.findall(r'([+-]?[\d.,]+)\s*%', str(value))
                if len(matches)>1:
                    raise ValueError('ambiguous percentages')
                value = number(matches[0]) if matches else number(value)
                if value < 0 or (key in ('win_rate', 'history_quality') and value > 100):
                    raise ValueError('invalid percentage')
            elif key in ('winning_trades', 'losing_trades') and isinstance(value, str) and '(' in value:
                match = re.fullmatch(r'\s*(\d+)\s*\([\d.,]+\s*%\)\s*', value)
                if not match:
                    raise ValueError('ambiguous trade count')
                value = number(match.group(1))
            else:
                value = number(value)
            if abs(value)>=1e100:
                raise ValueError('native sentinel or implausible magnitude')
            if key in COUNT_METRICS and (value < 0 or not value.is_integer()):
                raise ValueError('invalid trade count')
            if key in ('gross_profit', 'profit_factor', 'balance_drawdown_absolute', 'equity_drawdown_absolute') and value<0:
                raise ValueError('invalid sign')
            if key == 'gross_loss' and value>0:
                raise ValueError('ambiguous gross loss sign')
            metrics[key] = int(value) if key in COUNT_METRICS else value
            availability[key] = 'available'
        except (ValueError, TypeError):
            metrics[key] = None
            availability[key] = 'unavailable' if not values else 'inconclusive'
            issues.append(key + ': indisponivel ou inconclusivo')
    if metrics['gross_loss'] == 0:
        metrics['profit_factor'] = None
        availability['profit_factor'] = 'infinite' if (metrics['gross_profit'] or 0)>0 else 'undefined'
        issues.append('profit_factor: sem denominador de perdas; nenhum numero finito publicado')
    elif found.get('profit_factor') and str(found['profit_factor'][0]).strip().lower() in ('inf', '+inf', 'infinity', '+infinity', '∞'):
        metrics['profit_factor'] = None
        availability['profit_factor'] = 'infinite'
    if metrics['trades'] == 0:
        for key in ('win_rate', 'expected_payoff'):
            metrics[key] = None
            availability[key] = 'not_applicable'
        issues.append('win_rate/expected_payoff: sem operacoes')
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
    if isinstance(raw, dict) and (raw.get('complete') is False or raw.get('ok') is False):
        issues.append('report: fonte declarou resultado incompleto ou falha')
    return {'status': 'complete' if not issues else 'inconclusive', 'metrics': metrics,
            'availability': availability,
            'native_mapping': native_mapping, 'derived_metrics':derived_metrics,
            'source_values': {key:[str(value) for value in values] for key,values in found.items()},
            'period_results': periods, 'issues': issues}
