"""Read-only, opt-in audit of explicitly scoped order/deal evidence. No MT5 APIs.

Adapters must preserve source locators and explicitly declare trade groupings.
An evidence hash checks content integrity, not authenticity or runtime identity.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


EXIT_REASONS = ('strategy_signal', 'stop_loss', 'take_profit', 'period_end', 'other', 'unknown')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('boolean is not a numeric observation')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid numeric observation') from None
    if not result.is_finite() or abs(result) >= Decimal('1e100'):
        raise ValueError('non-finite or sentinel numeric observation')
    return result


def output(value):
    return float(value) if value is not None else None


def sha(value):
    if value is not None and (not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)):
        raise ValueError('invalid SHA256')
    return value


def audit_execution(evidence, *, expected_run_id):
    """Audit normalized observations; never infer an exit from P/L or a sell side.

    Required: schema_version=1.0, run_id, sources, orders, deals, groups,
    exit_events. A source is {payload, sha256}; rows/events have an evidence
    {source, locator}. orders/deals/groups may be None (unavailable), not zero.
    Group links are adapter assertions, not inferred native position IDs.
    """
    if not isinstance(evidence, dict) or evidence.get('schema_version') != '1.0':
        raise ValueError('unsupported execution evidence')
    if not isinstance(expected_run_id, str) or not expected_run_id or evidence.get('run_id') != expected_run_id:
        raise ValueError('execution evidence run_id mismatch')
    sources = evidence.get('sources')
    if not isinstance(sources, dict) or not sources:
        raise ValueError('source documents required')
    for source in sources.values():
        if not isinstance(source, dict) or sha(source.get('sha256')) is None or digest(source.get('payload')) != source['sha256']:
            raise ValueError('source document hash mismatch')
        payload = source.get('payload')
        if isinstance(payload, dict) and payload.get('run_id', expected_run_id) != expected_run_id:
            raise ValueError('source document run_id mismatch')

    def ref(row):
        r = row.get('evidence', {})
        if not isinstance(r, dict) or r.get('source') not in sources or not isinstance(r.get('locator'), str) or not r['locator']:
            raise ValueError('missing source locator')
        return deepcopy(r)

    def rows(name):
        values = evidence.get(name)
        if values is None:
            return None
        if not isinstance(values, list):
            raise ValueError('invalid observation collection')
        seen = set()
        for row in values:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or row['id'] in seen:
                raise ValueError('missing or duplicate observation ID')
            seen.add(row['id']); ref(row)
        return values

    orders, deals, groups = rows('orders'), rows('deals'), rows('groups')
    events = evidence.get('exit_events', [])
    if not isinstance(events, list):
        raise ValueError('invalid exit events')
    for event in events:
        if not isinstance(event, dict) or event.get('reason') not in EXIT_REASONS:
            raise ValueError('invalid exit reason')
        ref(event)
    issues, warnings, order_results, group_results = [], [], [], []
    for name, collection in (('orders', orders), ('deals', deals), ('groups', groups)):
        if collection is None:
            warnings.append(name + '_unavailable')
    order_map = {o['id']: o for o in orders or []}
    deal_map = {d['id']: d for d in deals or []}
    for event in events:
        if deals is not None and (event.get('deal_id') not in deal_map or
                deal_map[event['deal_id']].get('entry') != 'out'):
            issues.append('exit_event_has_no_exit_deal')
    for d in deals or []:
        volume = number(d.get('volume'))
        if volume is not None and volume <= 0:
            raise ValueError('deal volume must be positive')
        price = number(d.get('price'))
        if price is not None and price <= 0:
            raise ValueError('deal price must be positive')
        if volume is None or price is None:
            warnings.append('deal_execution_unverifiable:' + d['id'])
        if d.get('side') not in ('buy', 'sell', None) or d.get('entry') not in ('in', 'out', 'inout', None):
            raise ValueError('invalid deal side or entry')
        if d.get('entry') in ('inout', None):
            warnings.append('deal_entry_unresolved:' + d['id'])
        if orders is not None and d.get('order_id') not in order_map:
            issues.append('deal_has_no_matching_order:' + d['id'])
    complete = evidence.get('counts_complete') is True
    if not complete:
        warnings.append('collection_completeness_unverified')
    contract = number(evidence.get('contract_size'))
    if contract is not None and contract <= 0:
        raise ValueError('contract size must be positive')
    for o in orders or []:
        linked = [d for d in deals or [] if d.get('order_id') == o['id']]
        state = o.get('state')
        if state == 'rejected':
            warnings.append('order_rejected:' + o['id'])
        elif state in ('canceled', 'cancelled', 'expired'):
            warnings.append('order_' + state + ':' + o['id'])
        elif state in ('partial', 'partially_filled'):
            warnings.append('order_state_partial:' + o['id'])
        requested, filled = number(o.get('requested_volume')), number(o.get('filled_volume'))
        if requested is None or filled is None:
            warnings.append('order_volume_unverifiable:' + o['id'])
        if any(v is not None and v < 0 for v in (requested, filled)):
            raise ValueError('negative order volume')
        if requested is not None and filled is not None and filled > requested:
            issues.append('filled_exceeds_requested:' + o['id'])
        volumes = [number(d.get('volume')) for d in linked]
        total = sum(volumes, Decimal(0)) if linked and all(v is not None for v in volumes) else (Decimal(0) if deals == [] and complete else None)
        if total is not None and filled is not None and complete and total != filled:
            issues.append('order_deal_volume_mismatch:' + o['id'])
        if deals is not None and not linked and filled and complete:
            issues.append('filled_order_without_deals:' + o['id'])
        partial = requested is not None and filled is not None and 0 < filled < requested
        if partial:
            warnings.append('partial_execution:' + o['id'])
        if any(d.get('side') != o.get('side') or d.get('symbol') != o.get('symbol') for d in linked):
            issues.append('order_deal_side_or_symbol_mismatch:' + o['id'])
        prices = [number(d.get('price')) for d in linked]
        vwap = sum((p*v for p, v in zip(prices, volumes)), Decimal(0))/total if total and all(p is not None for p in prices) else None
        price = number(o.get('requested_price'))
        if price is not None and price < 0:
            raise ValueError('negative price reference')
        adverse = ((vwap-price) if o.get('side') == 'buy' else (price-vwap)) if price and price > 0 and vwap is not None and o.get('side') in ('buy', 'sell') else None
        if adverse:
            warnings.append('execution_price_differs:' + o['id'])
        order_results.append(dict(order_id=o['id'], filled_volume=output(filled), deal_volume=output(total),
            order_state=state, rejected=(state == 'rejected') if state in (
                'filled', 'partial', 'partially_filled', 'rejected', 'canceled', 'cancelled', 'expired', 'started', 'placed') else None,
            partial_execution=partial if requested is not None and filled is not None else None,
            requested_price=output(price), executed_vwap=output(vwap), adverse_price_difference=output(adverse),
            price_reference_kind=o.get('price_reference_kind', 'caller_declared_requested_price'),
            price_difference_pnl=output(-adverse*total*contract) if adverse is not None and total is not None and contract is not None else None,
            evidence=ref(o)))

    used = set()
    for group in (groups or []) if deals is not None else []:
        entry_ids, exit_ids = group.get('entry_deals'), group.get('exit_deals')
        if not isinstance(entry_ids, list) or not isinstance(exit_ids, list) or not entry_ids:
            raise ValueError('explicit entry/exit links required')
        ids = entry_ids + exit_ids
        if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('duplicate or invalid trade links')
        if used.intersection(ids):
            issues.append('deal_reused_across_groups:' + group['id'])
        used.update(ids)
        if any(i not in deal_map for i in ids):
            issues.append('group_has_unknown_deal:' + group['id']); continue
        entries, exits = [deal_map[i] for i in entry_ids], [deal_map[i] for i in exit_ids]
        direction = group.get('direction')
        if direction not in ('long', 'short'):
            raise ValueError('explicit position direction required')
        buy = direction == 'long'
        if any(d.get('entry') != 'in' or d.get('side') != ('buy' if buy else 'sell') for d in entries) or any(
                d.get('entry') != 'out' or d.get('side') != ('sell' if buy else 'buy') for d in exits):
            issues.append('position_direction_or_entry_mismatch:' + group['id'])
        if len({d.get('symbol') for d in entries+exits}) != 1:
            issues.append('group_symbol_mismatch:' + group['id'])
        iv, ov = [number(d.get('volume')) for d in entries], [number(d.get('volume')) for d in exits]
        volume_in = sum(iv, Decimal(0)) if all(v is not None for v in iv) else None
        volume_out = sum(ov, Decimal(0)) if exits and all(v is not None for v in ov) else (Decimal(0) if complete and not exits else None)
        closed = volume_in is not None and volume_in == volume_out
        if volume_in is not None and volume_out is not None and volume_out > volume_in:
            issues.append('exit_volume_exceeds_entry:' + group['id'])
        if not closed:
            warnings.append('position_open_or_partial:' + group['id'])
        matched = [e for e in events if e.get('deal_id') in exit_ids]
        # Every exit needs evidence. P/L, prices, and order comments alone do not classify a cause.
        reasons = {e['reason'] for e in matched if e['reason'] != 'unknown'}
        covered = all(any(e.get('deal_id') == i and e['reason'] != 'unknown' for e in matched)
                      for i in exit_ids) and bool(exit_ids)
        reason = next(iter(reasons)) if covered and len(reasons) == 1 else 'unknown'
        if len(reasons) > 1:
            warnings.append('conflicting_or_mixed_exit_reasons:' + group['id'])
        if reason == 'unknown':
            warnings.append('exit_reason_unverified:' + group['id'])
        profits = [number(d.get('profit')) for d in entries+exits]
        pnl = sum(profits, Decimal(0)) if all(p is not None for p in profits) else None
        group_results.append(dict(group_id=group['id'], direction=direction, closed=closed,
            volume_in=output(volume_in), volume_out=output(volume_out), exit_reason=reason,
            profit_recorded=output(pnl), pairing_provenance=group.get('pairing_provenance', 'caller_asserted'),
            evidence=ref(group), exit_evidence=[deepcopy(e) for e in matched]))
    if groups is not None and deals is not None and set(deal_map) != used:
        warnings.append('deals_not_fully_grouped')
    totals = {}
    for key in ('profit', 'commission', 'swap', 'fees'):
        values = [number(d.get(key)) for d in deals or []]
        totals[key] = sum(values, Decimal(0)) if deals and complete and all(v is not None for v in values) else None
    if totals['profit'] is None:
        warnings.append('recorded_profit_unavailable')
    costs_complete = evidence.get('costs_complete') is True and all(totals[k] is not None for k in ('commission', 'swap', 'fees'))
    net = sum(totals.values(), Decimal(0)) if costs_complete and totals['profit'] is not None else None
    reported = number(evidence.get('reported_net_profit'))
    if net is not None and reported is not None and abs(net-reported) > Decimal('0.01'):
        issues.append('deal_net_profit_mismatch')
    if not costs_complete:
        warnings.append('costs_unknown_or_incomplete')
    identity = evidence.get('identity', {})
    if not isinstance(identity, dict):
        raise ValueError('invalid identity observation')
    disk, runtime = sha(identity.get('disk_sha256')), sha(identity.get('runtime_sha256'))
    identity_status = 'unverified'
    if disk is not None and runtime is not None:
        # A runtime hash also needs an identified observation, not just two equal declarations.
        if identity.get('runtime_evidence'):
            ref({'evidence': identity['runtime_evidence']})
            identity_status = 'hash_match' if disk == runtime else 'hash_mismatch'
            if disk != runtime:
                issues.append('runtime_binary_hash_mismatch')
    if identity_status == 'unverified':
        warnings.append('runtime_binary_identity_unverified')
    size_disk, size_loaded = number(identity.get('disk_bytes')), number(identity.get('journal_loaded_bytes'))
    if any(v is not None and (v < 0 or v != v.to_integral_value()) for v in (size_disk, size_loaded)):
        raise ValueError('invalid byte count')
    size_difference = size_loaded-size_disk if size_disk is not None and size_loaded is not None else None
    if size_difference:
        warnings.append('loaded_size_semantics_unresolved')
    exclusions = [g for g in group_results if g['exit_reason'] == 'period_end']
    return dict(schema_version='1.0', artifact_type='execution_audit', run_id=expected_run_id,
        evidence_sha256=digest(evidence), source_hashes={k:v['sha256'] for k,v in sources.items()},
        status='inconsistent' if issues else ('partial' if warnings else 'consistent'),
        issues=sorted(set(issues)), warnings=sorted(set(warnings)), orders=order_results, trades=group_results,
        recorded_totals={k:output(v) for k,v in totals.items()}, net_after_all_costs=output(net),
        costs_complete=costs_complete, binary_identity=dict(status=identity_status,
            loaded_minus_disk_bytes=output(size_difference), loaded_size_measure='unverified',
            size_difference_proves_different_binary=False),
        period_end_diagnostic=dict(count=len(exclusions), profit_recorded=output(sum((number(g['profit_recorded']) for g in exclusions), Decimal(0))) if exclusions and all(g['profit_recorded'] is not None for g in exclusions) else None,
            warning='diagnostic_partition_only_not_an_alternative_backtest'),
        limitations=['source hashes do not prove authenticity or correct adapter mapping',
            'run scope and trade group links require caller audit', 'execution price differences do not establish a cause'])


def attach_execution_audit(summary, evidence):
    """Add a sidecar to summary 1.1 without changing any historical metric."""
    if summary.get('schema_version') != '1.1' or summary.get('artifact_type') != 'run_summary':
        raise ValueError('summary 1.1 required')
    audit = audit_execution(evidence, expected_run_id=summary.get('run_id'))
    result = deepcopy(summary)
    result['execution_audit'] = audit
    result['warnings'] = sorted(set(result['warnings'] + ['execution_audit:'+x for x in audit['issues']+audit['warnings']]))
    if audit['status'] == 'inconsistent':
        result['data_quality']['classification'] = 'invalid'
    elif audit['status'] != 'consistent' and result['data_quality']['classification'] == 'complete':
        result['data_quality']['classification'] = 'partial'
    return result
