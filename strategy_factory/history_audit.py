"""Offline market-history audit. Observed consistency never certifies coverage."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re

from .analysis import decode_artifact
from .batch_manifest import fingerprint,identifier

STAMP=re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$')
BAR_FIELDS=('open','high','low','close','tick_volume','volume','spread')


def _number(value,*,positive=False,integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0 or positive and value==0 or integer and int(value)!=value:
        raise ValueError('invalid finite nonnegative market number')
    return value


def _stamp(value):
    if not isinstance(value,str) or not STAMP.fullmatch(value):raise ValueError('full ISO timestamp required')
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def _key(stamp):
    return stamp.astimezone(timezone.utc).isoformat() if stamp.tzinfo is not None else stamp.isoformat()


def audit_snapshot(snapshot,*,source_id,kind='bars',timezone_label='unknown',capture_time=None,file_sha256=None,origin='local_saved_response_provider_unverified'):
    """Audit submitted rows without repairing, sorting away errors or filling gaps.

    kind separates broker-reported ticks from generated ticks. Unknown broker
    timezone stays unknown. Source origin is an assertion, not authenticity proof.
    """
    identifier(source_id)
    if not isinstance(origin,str) or not origin:raise ValueError('explicit origin description required')
    if kind not in ('bars','broker_ticks','generated_ticks') or timezone_label not in ('unknown','UTC','explicit_offsets'):
        raise ValueError('explicit supported data kind/timezone policy required')
    if capture_time is not None:
        if _stamp(capture_time).tzinfo is None:raise ValueError('capture time must include offset')
    if not isinstance(snapshot,dict) or snapshot.get('symbol')!='PETR4' or snapshot.get('period') not in ('M1','M5','tick'):
        raise ValueError('PETR4 M1/M5/tick snapshot required')
    period=snapshot['period']
    if (kind=='bars')!=(period in ('M1','M5')):raise ValueError('tick/bar kind mismatch')
    errors=[];warnings=[];records=[];previous=None;modes=set();seen={};duplicates=0
    if snapshot.get('ok') is not True:errors.append(dict(code='unsuccessful_snapshot'))
    if snapshot.get('truncated') is True or snapshot.get('complete') is False:errors.append(dict(code='explicitly_incomplete_snapshot'))
    rows=snapshot.get('history')
    if not isinstance(rows,list):errors.append(dict(code='missing_history_array'));rows=[]
    if timezone_label=='unknown':warnings.append('broker_timezone_unknown')
    if capture_time is None:warnings.append('capture_time_unknown_file_mtime_is_not_capture_time')
    for index,row in enumerate(rows):
        try:
            if not isinstance(row,dict):raise ValueError('row must be object')
            stamp=_stamp(row.get('time'));aware=stamp.tzinfo is not None;modes.add('aware' if aware else 'naive')
            if timezone_label=='UTC' and (not aware or stamp.utcoffset()!=timedelta(0)):
                raise ValueError('timestamp conflicts with UTC declaration')
            if timezone_label=='explicit_offsets' and not aware:raise ValueError('timestamp offset missing')
            if previous is not None:
                if (previous.tzinfo is None)!= (stamp.tzinfo is None):raise ValueError('mixed aware/naive timestamps')
                if stamp<previous:errors.append(dict(code='chronological_reversal',row=index))
            previous=stamp
            key=_key(stamp)
            if kind=='bars':
                step=1 if period=='M1' else 5
                if stamp.second or stamp.microsecond or stamp.minute%step:raise ValueError('bar grid misalignment')
                values={k:_number(row.get(k),positive=k in ('open','high','low','close'),integer=k=='tick_volume') for k in BAR_FIELDS}
                if not values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']:
                    raise ValueError('invalid OHLC enclosure')
                normalized=dict(time=key,local_date=_stamp(key).date().isoformat(),**values)
                if key in seen:
                    duplicates+=1
                    if seen[key]!=fingerprint(normalized):errors.append(dict(code='conflicting_duplicate',row=index))
                seen.setdefault(key,fingerprint(normalized))
            else:
                quotes={k:_number(row[k]) for k in ('bid','ask','last') if k in row}
                if not any(v>0 for v in quotes.values()):raise ValueError('no usable quote/last price')
                if quotes.get('bid',0)>0 and quotes.get('ask',0)>0 and quotes['ask']<quotes['bid']:
                    raise ValueError('crossed bid/ask')
                if 'volume' in row:_number(row['volume'])
                if 'time_msc' in row:
                    _number(row['time_msc'],integer=True)
                    if aware and int(stamp.timestamp())!=row['time_msc']//1000:raise ValueError('time/time_msc mismatch')
                    if not aware:warnings.append('time_msc_alignment_unverified_without_broker_timezone')
                normalized=dict(row,time=key,local_date=_stamp(key).date().isoformat())
                # Same timestamp may legitimately contain multiple different ticks.
                signature=fingerprint(normalized)
                if signature in seen:duplicates+=1;warnings.append('identical_tick_record_duplicate_or_indistinguishable_event')
                seen[signature]=signature
            records.append(normalized)
        except (ValueError,TypeError,OverflowError) as exc:
            errors.append(dict(code='invalid_row',row=index,detail=str(exc)))
    if len(modes)>1:errors.append(dict(code='mixed_timestamp_semantics'))
    ordered=sorted({r['time'] for r in records})
    gaps=[]
    if kind=='bars':
        seconds=60 if period=='M1' else 300
        for left,right in zip(ordered,ordered[1:]):
            a,b=_stamp(left),_stamp(right)
            # String ordering cannot establish chronological continuity across mixed offsets/naivety.
            if (a.tzinfo is None)!=(b.tzinfo is None):continue
            delta=(b-a).total_seconds()
            if delta>seconds:
                same_date=a.date()==b.date()
                gaps.append(dict(from_time=left,to_time=right,seconds=delta,
                    classification='unclassified_intraday_interval' if same_date else 'unclassified_between_dates',
                    omitted_grid_slots=int(delta//seconds)-1 if same_date else None,
                    certified_missing_bars=None))
    days=Counter(r['local_date'] for r in {r['time']:r for r in records}.values()) if kind=='bars' else Counter(r['local_date'] for r in records)
    sessions={day:dict(rows=count,first=min(r['time'] for r in records if r['local_date']==day),
                      last=max(r['time'] for r in records if r['local_date']==day)) for day,count in sorted(days.items())}
    return dict(schema_version='3.3E-audit-1',artifact_type='history_snapshot_audit',source_id=source_id,
        symbol='PETR4',timeframe=period,kind=kind,timezone=timezone_label,capture_time=capture_time,
        origin=origin,
        date_basis='UTC' if modes=={'aware'} else 'unverified_source_clock',
        file_sha256=file_sha256,payload_sha256=fingerprint(snapshot),input_rows=len(rows),valid_rows=len(records),
        duplicate_rows=duplicates,errors=errors,warnings=sorted(set(warnings)),sessions=sessions,intervals=gaps,
        classification='invalid' if errors else 'observed_partial',coverage_certified=False,
        advertised_available_from=snapshot.get('data_available_from'),records=records,
        volume_observations=dict(zero_tick_volume=sum(r.get('tick_volume')==0 for r in records),
            zero_real_volume=sum(r.get('volume')==0 for r in records),
            ranges={k:dict(minimum=min((r[k] for r in records if k in r),default=None),maximum=max((r[k] for r in records if k in r),default=None)) for k in ('tick_volume','volume','spread')}),
        live_execution_enabled=False)


def audit_local_file(path,*,source_id,expected_file_sha256=None,**kwargs):
    """Read bytes once. Raw and canonical hashes have different explicit meanings."""
    data=Path(path).read_bytes();checksum=hashlib.sha256(data).hexdigest()
    if expected_file_sha256 is not None and checksum!=expected_file_sha256:raise ValueError('source bytes changed')
    text=data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    return audit_snapshot(decode_artifact(text),source_id=source_id,file_sha256=checksum,**kwargs)


def audit_collection(audits):
    audits=list(audits);groups=defaultdict(dict);duplicates=Counter();conflicts=[]
    if not audits or len({a['source_id'] for a in audits})!=len(audits):raise ValueError('unique nonempty source collection required')
    for audit in audits:
        if audit.get('schema_version')!='3.3E-audit-1' or audit.get('coverage_certified') is not False:
            raise PermissionError('unverified snapshot audit required; no implicit certification')
        key=(audit['symbol'],audit['timeframe'],audit['kind'],audit['timezone'],audit['date_basis'])
        for row in audit['records']:
            identity=row['time'] if audit['kind']=='bars' else fingerprint(row)
            if identity in groups[key]:
                duplicates[audit['timeframe']]+=1
                if fingerprint(groups[key][identity])!=fingerprint(row):conflicts.append(dict(time=identity,source=audit['source_id']))
            else:groups[key][identity]=row
    series=[]
    for (symbol,period,kind,zone,basis),records in sorted(groups.items()):
        rows=sorted(records.values(),key=lambda r:r['time'])
        series.append(dict(symbol=symbol,timeframe=period,kind=kind,timezone=zone,date_basis=basis,unique_rows=len(rows),
            first=rows[0]['time'] if rows else None,last=rows[-1]['time'] if rows else None,
            bars_by_day=dict(sorted(Counter(r['local_date'] for r in rows).items())),records=rows))
    # Empty sources are still visible through the per-source descriptors.
    comparisons=[]
    for zone,basis in sorted({(s['timezone'],s['date_basis']) for s in series}):
        m1={r['time']:r for s in series if s['timeframe']=='M1' and s['timezone']==zone and s['date_basis']==basis for r in s['records']}
        m5={r['time']:r for s in series if s['timeframe']=='M5' and s['timezone']==zone and s['date_basis']==basis for r in s['records']}
        for key,row in m5.items():
            start=_stamp(key);keys=[_key(start+timedelta(minutes=i)) for i in range(5)]
            count=sum(k in m1 for k in keys)
            if count==0:continue
            result=dict(m5_time=key,timezone=zone,m1_rows=count,classification='incomplete_M1_bucket',differences=[],spread_aggregation_not_inferred=True)
            if count==5:
                minute=[m1[k] for k in keys]
                expected=dict(open=minute[0]['open'],close=minute[-1]['close'],high=max(r['high'] for r in minute),low=min(r['low'] for r in minute),
                              tick_volume=sum(r['tick_volume'] for r in minute),volume=sum(Decimal(str(r['volume'])) for r in minute))
                result['differences']=[field for field,v in expected.items() if Decimal(str(row[field]))!=Decimal(str(v))]
                result['classification']='mismatch' if result['differences'] else 'conditional_aggregate_match'
            comparisons.append(result)
    return dict(schema_version='3.3E-collection-1',artifact_type='history_collection_audit',series=series,
        sources=[{k:deepcopy(a[k]) for k in ('source_id','file_sha256','payload_sha256','origin','kind','timeframe','timezone','date_basis','capture_time','input_rows','valid_rows','classification')} for a in audits],
        cross_source_duplicates=dict(duplicates),conflicting_duplicates=conflicts,
        source_errors={a['source_id']:a['errors'] for a in audits if a['errors']},
        M1_M5_comparison=comparisons,comparison_semantics='conditional_same_declared_local_clock_not_verified_broker_timezone_or_price_basis',
        classification='invalid' if conflicts or any(a['errors'] for a in audits) or any(c['classification']=='mismatch' for c in comparisons) else 'observed_partial',
        coverage_certified=False,live_execution_enabled=False)


def certify_history(*args,**kwargs):
    raise PermissionError('offline consistency audit cannot certify source authenticity, sessions or completeness')
