"""Read-only reconciliation: native evidence and calculations never replace metrics.

Journal input MUST be bounded to one run before calling this API; matching run IDs
are explicit provenance assertions by the caller, not inferred from timestamps.
"""
import math
import re

from .reports import ALIASES, analyze_report, number


def journal_statistics(journal):
    """Parse only the Homologacao_002 marker and MT5 final balance/quality messages."""
    if isinstance(journal, dict):
        messages = [record.get('message', '') for record in journal.get('records', [])]
    elif isinstance(journal, str):
        messages = journal.splitlines()
    else:
        messages = []
    values = {}
    for message in messages:
        marker = re.search(r'MT5SF002 STAT name=([a-z_]+) value=(\S+)', message)
        if marker and marker[1] in ALIASES:
            values.setdefault(marker[1], []).append(marker[2])
        balance = re.fullmatch(r'final balance ([+-]?[\d., ]+) ([A-Z]{3})', message.strip())
        if balance:
            values.setdefault('final_balance', []).append(balance[1])
        quality = re.fullmatch(r'quality of analyzed history is ([\d.]+)%', message.strip())
        if quality:
            values.setdefault('history_quality', []).append(quality[1])
    stats, issues = {}, []
    for key, entries in values.items():
        if all(value=='UNAVAILABLE' for value in entries):
            continue
        try:
            parsed = [number(value) for value in entries]
            # Equal repeated terminal/agent markers are acceptable; conflicting ones aren't.
            if not parsed or max(parsed)-min(parsed)>0.00000001:
                raise ValueError('conflicting journal values')
            stats[key] = parsed[0]
        except ValueError:
            issues.append(key + ': journal indisponivel ou conflitante')
    return analyze_report({'statistics':stats}), issues


def validate_financial(source, *, journal=None, run_id=None, journal_run_id=None,
                       native_reference=None, reference_run_id=None,
                       money_tolerance=0.01, ratio_tolerance=0.01):
    """Compare explicit report fields with a separately exported native report/journal.

    Calculated identities check consistency, not performance or deal attribution.
    A missing metric stays missing even when a reference/calculation supplies it.
    """
    if not all(math.isfinite(v) and v>=0 for v in (money_tolerance, ratio_tolerance)):
        raise ValueError('invalid tolerance')
    report = analyze_report(source)
    checks = []

    def compare(name, left, right, tolerance, source_name):
        state = 'unavailable' if left is None or right is None else (
            'match' if abs(left-right)<=tolerance+1e-10 else 'divergent')
        checks.append({'metric':name, 'source':source_name, 'report':left,
                       'reference':right, 'tolerance':tolerance, 'status':state})

    def tolerance(key):
        return 0 if key in ('trades','deals','orders','positions','winning_trades','losing_trades') else (
            ratio_tolerance if key in ('profit_factor','win_rate','history_quality') or key.endswith('_relative') else money_tolerance)

    provenance_issues = []
    completeness_issues = []
    if isinstance(source, dict) and run_id is not None and str(source.get('run_id',run_id))!=str(run_id):
        provenance_issues.append('report run_id mismatch')
    journal_analysis = None
    if journal is not None:
        if isinstance(journal,dict) and journal.get('truncated') is True:
            completeness_issues.append('journal truncado; comparacao parcial')
        if run_id is None or str(journal_run_id)!=str(run_id) or provenance_issues:
            provenance_issues.append('journal sem vinculo comprovado ao run_id solicitado')
        else:
            journal_analysis, errors = journal_statistics(journal)
            provenance_issues.extend(errors)
            for key in ALIASES:
                compare(key, report['metrics'][key], journal_analysis['metrics'][key], tolerance(key), 'journal')
            for key,derived in report.get('derived_metrics',{}).items():
                compare(key,derived['value'],journal_analysis['metrics'][key],tolerance(key),'native_calculation_vs_journal')
    reference = None
    if native_reference is not None:
        if run_id is None or str(reference_run_id)!=str(run_id) or provenance_issues:
            provenance_issues.append('reference sem vinculo comprovado ao run_id solicitado')
        else:
            reference = analyze_report(native_reference)
            if isinstance(native_reference, dict) and str(native_reference.get('run_id',run_id))!=str(run_id):
                provenance_issues.append('native reference run_id mismatch')
                reference = None
            else:
                for key in ALIASES:
                    compare(key, report['metrics'][key], reference['metrics'][key], tolerance(key), 'native_reference')
    m = report['metrics']
    def identity(name, observed, operands, calculate, tol=money_tolerance):
        expected = None
        if all(v is not None for v in operands):
            expected = calculate(*operands)
        compare(name, observed, expected, tol, 'calculated_identity')
    identity('net_profit',m['net_profit'],[m['gross_profit'],m['gross_loss']],lambda a,b:a+b)
    identity('profit_factor',m['profit_factor'],[m['gross_profit'],m['gross_loss']],lambda a,b:a/abs(b) if b<0 else None,ratio_tolerance)
    identity('expected_payoff',m['expected_payoff'],[m['net_profit'],m['trades']],lambda a,b:a/b if b>0 else None)
    identity('win_rate',m['win_rate'],[m['winning_trades'],m['trades']],lambda a,b:100*a/b if b>0 else None,ratio_tolerance)
    # Do not assume final balance = initial + profit: withdrawals/credits may exist.
    if all(m[key] is not None for key in ('winning_trades','losing_trades','trades')):
        classified = m['winning_trades']+m['losing_trades']
        checks.append({'metric':'trade_classification', 'source':'calculated_identity',
                       'status':'match' if classified<=m['trades'] else 'divergent',
                       'unclassified_trades':max(0,m['trades']-classified)})
    divergent = bool(provenance_issues) or any(c['status']=='divergent' for c in checks)
    compared = [c for c in checks if c['source']!='calculated_identity' and c['status']=='match']
    # Partial evidence never promotes a report to fully verified.
    verified = compared and all(c['status']=='match' for c in checks if c['source']!='calculated_identity')
    reference_complete = reference is None or reference['status']=='complete'
    status = 'divergent' if divergent else ('verified' if verified and report['status']=='complete'
                     and reference_complete and not completeness_issues else 'inconclusive')
    return {'status':status, 'report':report, 'journal':journal_analysis,
            'native_reference':reference, 'checks':checks, 'issues':provenance_issues+completeness_issues}


def main():
    """Offline comparison CLI; output is exclusive and no MCP tools are invoked."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--journal', type=Path)
    parser.add_argument('--journal-run-id')
    parser.add_argument('--native-reference', type=Path)
    parser.add_argument('--reference-run-id')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        if path is None:
            return None
        data = path.read_bytes()
        text = data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        if text.lstrip().startswith('{'):
            value = json.loads(text)
            if isinstance(value, dict) and 'structuredContent' in value:
                return value['structuredContent']
            if isinstance(value, dict) and len(value.get('content', []))==1:
                block = value['content'][0]
                if block.get('type')=='text':
                    return json.loads(block['text'])
            return value
        return text
    result = validate_financial(read(args.report),journal=read(args.journal),run_id=args.run_id,
             journal_run_id=args.journal_run_id,native_reference=read(args.native_reference),
             reference_run_id=args.reference_run_id)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(result['status'])


if __name__=='__main__':
    main()
