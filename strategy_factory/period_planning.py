"""Local snapshot coverage and non-executable chronological period candidates."""
from collections import Counter
from datetime import date,datetime,timedelta
from copy import deepcopy

from .batch_manifest import fingerprint
from .batch_safety import validate_periods

KNOWN_RESULTS=('2026-11-03','2026-11-07')  # Half-open, already observed results.


def inventory_local_history(snapshots):
    """No terminal, downloads, filesystem writes or inference from advertised start."""
    bars={};ticks=[];sources=[];conflicts=set()
    for snapshot in snapshots:
        if not isinstance(snapshot,dict) or snapshot.get('symbol')!='PETR4' or snapshot.get('period') not in ('M5','tick') or snapshot.get('ok') is not True:
            raise ValueError('successful local PETR4 M5/tick snapshot required')
        rows=snapshot.get('history')
        if not isinstance(rows,list):raise ValueError('history list required')
        previous=None
        for row in rows:
            stamp=row.get('time')
            if not isinstance(stamp,str):raise ValueError('timestamp missing')
            parsed=datetime.fromisoformat(stamp)
            if parsed.tzinfo is not None:raise ValueError('preserve timezone-free terminal timestamps without invented conversion')
            if previous is not None and parsed<previous:raise ValueError('history not ordered')
            previous=parsed
            if snapshot['period']=='M5':
                if parsed.minute%5 or parsed.second or stamp in bars and fingerprint(bars[stamp])!=fingerprint(row):
                    conflicts.add(stamp)
                bars.setdefault(stamp,deepcopy(row))
            else:ticks.append(stamp)
        sources.append(dict(sha256=fingerprint(snapshot),period=snapshot['period'],rows=len(rows),
            advertised_available_from=snapshot.get('data_available_from'),first=rows[0]['time'] if rows else None,
            last=rows[-1]['time'] if rows else None))
    days=Counter(t[:10] for t in bars)
    return dict(schema_version='3.3D-1',symbol='PETR4',timeframe='M5',unique_bars=len(bars),
        bars_by_day=dict(sorted(days.items())),observed_tick_records=len(ticks),
        first_tick=min(ticks) if ticks else None,last_tick=max(ticks) if ticks else None,
        conflicts=sorted(conflicts),sources=sources,session_completeness_verified=False,
        m1_generation_inputs_verified=False,real_tick_completeness_verified=False,
        advertised_start_is_not_coverage=True)


def validate_candidate_periods(periods):
    intervals=validate_periods(periods)
    final=intervals['final_test']
    if final and final['warmup_from']<KNOWN_RESULTS[1] and final['to_date']>KNOWN_RESULTS[0]:
        raise ValueError('known November result window cannot be independent final test, including warmup')
    return intervals


def propose_periods(coverage,*,warmup_bars=53):
    """Select candidates by chronology/coverage only, never accept profit inputs.

    Known-result days are excluded; two earliest disjoint calendar-week blocks
    with a complete observed warmup prefix are candidate development/OOS blocks.
    All remain unverified and require human review. A final period is not guessed.
    """
    if type(warmup_bars) is not int or warmup_bars<53:raise ValueError('at least 53 closed warmup bars required by existing EAs')
    if coverage.get('conflicts'):raise ValueError('conflicting local bars block period selection')
    blocks={}
    for day,count in sorted(coverage['bars_by_day'].items()):
        if KNOWN_RESULTS[0]<=day<KNOWN_RESULTS[1]:continue
        parsed=date.fromisoformat(day);week=parsed-timedelta(days=parsed.weekday())
        blocks.setdefault(week,[]).append((day,count))
    candidates=[]
    for days in blocks.values():
        prefix=0
        for index,(_,count) in enumerate(days):
            prefix+=count
            if prefix>=warmup_bars:
                if index+1<len(days):
                    interval=dict(warmup_from=days[0][0],from_date=days[index+1][0],
                        to_date=(date.fromisoformat(days[-1][0])+timedelta(days=1)).isoformat(),
                        history_status='unverified',selection_basis='prospective_not_result_selected')
                    candidates.append(dict(interval=interval,warmup_bars=prefix,
                        evaluation_bars=sum(n for _,n in days[index+1:])))
                break
    periods=dict(development=candidates[0]['interval'] if candidates else None,
                 out_of_sample=candidates[1]['interval'] if len(candidates)>1 else None,final_test=None)
    validate_candidate_periods(periods)
    return dict(schema_version='3.3D-1',proposal_only=True,live_execution_enabled=False,periods=periods,
        candidate_counts=candidates[:2],coverage_sha256=fingerprint(coverage),
        known_result_window_excluded=list(KNOWN_RESULTS),frozen=False,
        prior_data_exposure_requires_review=True,
        blockers=['independent_final_period_missing','session_completeness_unverified',
                  'M1_generation_inputs_unverified_for_every_tick_model','human_prospective_freeze_missing'])
