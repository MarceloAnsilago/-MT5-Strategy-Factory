"""Bounded acquisition proposals and an exclusively synthetic acquisition lab.

No MCP import, real consent issuer, callable transport or execution permission.
Human approval of a proposal requires a later operational implementation/review.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PureWindowsPath
import time

from .analysis import decode_artifact, read_artifact, write_artifact
from .batch_manifest import exact, fingerprint, sha, timestamp
from .history_audit import audit_snapshot, audit_collection
from .period_planning import validate_candidate_periods

STATES = ('ACQUISITION_PLAN_READY', 'AWAITING_HUMAN_APPROVAL',
          'ACQUISITION_BLOCKED', 'DATASET_PARTIAL', 'DATASET_AUDITED')
CHECKS = ('origin', 'broker_timezone', 'calendar_sessions', 'session_continuity',
          'M1_M5_compatibility', 'warmup_coverage', 'price_adjustments', 'corporate_events')
DESTINATION = r'C:\estrategia\runs\history_acquisition'
PROHIBITED = ('backtests', 'optimizations', 'compilations', 'orders',
              'execution_reservations', 'ea_parameter_changes')


def acquisition_proposal(connection):
    """Availability and date interpretation are deliberately not inferred."""
    body = dict(schema_version='3.3F-plan-1', symbol='PETR4', source='Rico-DEMO',
        connection=deepcopy(connection), tools=['get_chart_history'], timeframes=['M1', 'M5'],
        datetime_from='2024-01-01T00:00:00', datetime_to='2026-10-01T00:00:00',
        date_interpretation='broker_clock_unverified', implicit_sync_possible=True,
        local_only_guaranteed=False, page_days=1, limit_per_call=2000,
        destination=DESTINATION, max_calls=2100, max_records=1800000,
        max_raw_page_bytes=2097152, max_storage_bytes=2147483648,
        min_free_disk_bytes=4294967296, max_elapsed_seconds=21600,
        authorization_max_hours=24, automatic_retries=False, max_concurrency=1,
        tick_option_included=False, live_execution_enabled=False,
        prohibited_actions=list(PROHIBITED), availability_verified=False,
        periods=dict(
            development=dict(warmup_from='2024-01-01', from_date='2024-02-01',
                to_date='2025-07-01', history_status='unverified', selection_basis='prospective_not_result_selected'),
            out_of_sample=dict(warmup_from='2025-07-01', from_date='2025-08-01',
                to_date='2026-06-01', history_status='unverified', selection_basis='prospective_not_result_selected'),
            final_test=dict(warmup_from='2026-06-01', from_date='2026-07-01',
                to_date='2026-10-01', history_status='unverified', selection_basis='prospective_not_result_selected')))
    validate_proposal(body)
    return body


def validate_proposal(plan):
    keys = {'schema_version','symbol','source','connection','tools','timeframes',
        'datetime_from','datetime_to','date_interpretation','implicit_sync_possible',
        'local_only_guaranteed','page_days','limit_per_call','destination','max_calls',
        'max_records','max_raw_page_bytes','max_storage_bytes','min_free_disk_bytes',
        'max_elapsed_seconds','authorization_max_hours','automatic_retries','max_concurrency',
        'tick_option_included','live_execution_enabled','prohibited_actions','availability_verified','periods'}
    exact(plan, keys, 'acquisition proposal')
    if (plan['schema_version'] != '3.3F-plan-1' or plan['symbol'] != 'PETR4' or
        plan['source'] != 'Rico-DEMO' or plan['tools'] != ['get_chart_history'] or
        plan['timeframes'] != ['M1','M5'] or plan['destination'] != DESTINATION):
        raise ValueError('unsupported acquisition scope')
    for key, expected in dict(implicit_sync_possible=True, local_only_guaranteed=False,
        automatic_retries=False, tick_option_included=False, live_execution_enabled=False,
        availability_verified=False).items():
        if plan[key] is not expected: raise PermissionError('unsafe acquisition policy: '+key)
    if plan['prohibited_actions'] != list(PROHIBITED) or plan['date_interpretation'] != 'broker_clock_unverified':
        raise PermissionError('scope cannot grant execution or invent broker timezone')
    exact(plan['connection'], {'server','build','installation_sha256'}, 'acquisition connection')
    if plan['connection']['server'] != 'Rico-DEMO' or type(plan['connection']['build']) is not int or plan['connection']['build'] < 1:
        raise ValueError('explicit demo terminal identity required')
    sha(plan['connection']['installation_sha256'])
    if plan['connection']['installation_sha256'] is None: raise ValueError('installation identity missing')
    for key in ('page_days','limit_per_call','max_calls','max_records','max_raw_page_bytes',
                'max_storage_bytes','min_free_disk_bytes','max_elapsed_seconds','authorization_max_hours','max_concurrency'):
        if type(plan[key]) is not int or plan[key] < 1: raise ValueError('invalid limit: '+key)
    if (plan['page_days'] != 1 or plan['limit_per_call'] > 2000 or
        plan['max_concurrency'] != 1 or plan['authorization_max_hours'] > 24 or
        plan['max_raw_page_bytes'] > plan['max_storage_bytes']): raise ValueError('unsafe page or resource budget')
    start, end = (datetime.fromisoformat(plan[k]) for k in ('datetime_from','datetime_to'))
    if start.tzinfo is not None or end.tzinfo is not None or start.time() != datetime.min.time() or end.time() != datetime.min.time() or start >= end:
        raise ValueError('whole broker-clock dates required; timezone still unverified')
    periods = validate_candidate_periods(plan['periods'])
    for period in periods.values():
        if period is None or not start.date().isoformat() <= period['warmup_from'] < period['to_date'] <= end.date().isoformat():
            raise ValueError('period outside acquisition scope')
    count = (end-start).days * len(plan['timeframes'])
    worst_rows = (end-start).days * (1440+288)
    if count > plan['max_calls'] or worst_rows > plan['max_records']:
        raise ValueError('budget cannot cover calendar-grid envelope')
    return deepcopy(plan)


def page_requests(plan):
    plan = validate_proposal(plan)
    cursor = datetime.fromisoformat(plan['datetime_from'])
    end = datetime.fromisoformat(plan['datetime_to'])
    requests = []
    while cursor < end:
        following = min(cursor+timedelta(days=1), end)
        for period in plan['timeframes']:
            requests.append(dict(symbol=plan['symbol'], period=period,
                datetime_from=cursor.isoformat(), datetime_to=following.isoformat(), limit=plan['limit_per_call']))
        cursor = following
    return requests


def plan_status(plan, *, awaiting_approval=False):
    validate_proposal(plan)
    return dict(state='AWAITING_HUMAN_APPROVAL' if awaiting_approval else 'ACQUISITION_PLAN_READY',
        plan_sha256=fingerprint(plan), acquisition_enabled=False, live_execution_enabled=False,
        date_interpretation_verified=False, coverage_available=None)


class BlockedHistoryAdapter:
    """No dispatcher is stored. Even supplied human approval cannot enable it."""
    live_execution_enabled = False

    def acquire(self, *args, **kwargs):
        raise PermissionError('ACQUISITION_BLOCKED: separate human approval and reviewed real transport required')


def validate_fixture_consent(record, plan, *, now):
    """Synthetic fixture only; arbitrary actor strings cannot authenticate humans."""
    validate_proposal(plan)
    if not isinstance(record, dict): raise PermissionError('offline consent fixture required')
    exact(record, {'schema_version','purpose','plan_sha256','issued_at','expires_at',
                   'actor','statement','live_execution_enabled'}, 'synthetic acquisition consent')
    digest = fingerprint(plan)
    if (record['schema_version'] != '3.3F-consent-fixture-1' or record['purpose'] != 'synthetic_offline_only' or
        record['plan_sha256'] != digest or record['actor'] != 'synthetic-human-reviewer' or
        record['statement'] != 'SYNTHETIC ACQUISITION ONLY '+digest or record['live_execution_enabled'] is not False):
        raise PermissionError('real or mismatched authorization is not accepted in this laboratory')
    issued, expires = timestamp(record['issued_at']), timestamp(record['expires_at'])
    if not issued <= now < expires or expires-issued > timedelta(hours=plan['authorization_max_hours']):
        raise PermissionError('consent fixture expired, premature or excessively long')


class SyntheticHistorySource:
    """Finite data mapping, never a callback, network transport or MCP endpoint."""
    def __init__(self, pages):
        self.pages = deepcopy(pages)
        self.calls = []

    def fetch(self, request):
        key = fingerprint(request)
        self.calls.append(key)
        page = self.pages[key]
        if isinstance(page, Exception): raise page
        return deepcopy(page)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf-8')


class OfflineHistoryAcquisition:
    """Single-writer, append-only laboratory. Commit receipt follows raw+audit.

    An orphaned page, damaged receipt, altered bytes or unknown file blocks resume.
    Nothing is deleted/retried automatically. Cooperative stop cannot kill an RPC.
    """
    MARKER = dict(schema_version='3.3F-lab-1', synthetic_only=True, live_execution_enabled=False)

    def __init__(self, root, plan, consent, *, now, reopen=False):
        self.plan = validate_proposal(plan)
        validate_fixture_consent(consent, plan, now=now)
        self.consent = deepcopy(consent)
        self.root = Path(root)
        # Operational destination is reserved for a later reviewed implementation.
        if PureWindowsPath(str(root)).is_relative_to(PureWindowsPath(DESTINATION)):
            raise PermissionError('synthetic lab cannot write the operational destination')
        self.requests = page_requests(plan)
        self.state = 'DATASET_PARTIAL'
        self.marker = dict(self.MARKER, plan_sha256=fingerprint(plan), consent_sha256=fingerprint(consent))
        if reopen:
            if read_artifact(self.root/'synthetic_only.json') != self.marker:
                raise PermissionError('laboratory version or consent changed')
        else:
            self.root.mkdir(parents=True, exist_ok=False)
            write_artifact(self.root/'synthetic_only.json', self.marker)
        self._load()

    def _load(self):
        self.audits = []
        self.receipts = []
        self.rows = self.storage = 0
        self.elapsed = 0
        entries = sorted(p for p in self.root.iterdir() if p.name != 'synthetic_only.json')
        for index, folder in enumerate(entries):
            if folder.name != f'page-{index:06d}' or not folder.is_dir() or index >= len(self.requests):
                raise ValueError('unknown, noncontiguous or excess laboratory page')
            if {p.name for p in folder.iterdir()} != {'request.json','raw.json','audit.json','receipt.json'}:
                raise ValueError('uncommitted/orphaned page blocks resume; manual recovery required')
            receipt = read_artifact(folder/'receipt.json')
            digest = receipt.pop('receipt_sha256')
            if fingerprint(receipt) != digest: raise ValueError('receipt hash mismatch')
            raw = (folder/'raw.json').read_bytes()
            audit_bytes = (folder/'audit.json').read_bytes()
            expected_previous = self.receipts[-1]['receipt_sha256'] if self.receipts else None
            intent = read_artifact(folder/'request.json')
            if (receipt['request'] != self.requests[index] or receipt['plan_sha256'] != fingerprint(self.plan) or
                receipt['consent_sha256'] != fingerprint(self.consent) or receipt['previous_receipt_sha256'] != expected_previous or
                intent != dict(request=self.requests[index], plan_sha256=fingerprint(self.plan),
                               consent_sha256=fingerprint(self.consent), synthetic_only=True) or
                hashlib.sha256(raw).hexdigest() != receipt['raw_sha256'] or
                hashlib.sha256(audit_bytes).hexdigest() != receipt['audit_sha256']):
                raise ValueError('page identity, version, provenance or bytes changed')
            audit = self._inspect(raw, self.requests[index], index, receipt['captured_at'])
            if fingerprint(audit) != fingerprint(decode_artifact(audit_bytes.decode('utf-8'))):
                raise ValueError('stored audit does not match raw page')
            if receipt['record_count'] != audit['input_rows']: raise ValueError('record count changed')
            receipt['receipt_sha256'] = digest
            self.audits.append(audit); self.receipts.append(receipt)
            self.rows += audit['input_rows']
            self.elapsed += receipt['elapsed_seconds']
            self.storage += sum(p.stat().st_size for p in folder.iterdir())
        if self.rows > self.plan['max_records'] or self.storage > self.plan['max_storage_bytes']:
            raise ValueError('persisted data exceeds approved budget')

    def _inspect(self, raw, request, index, captured_at):
        if len(raw) > self.plan['max_raw_page_bytes']: raise ValueError('page byte limit exceeded')
        payload = decode_artifact(raw.decode('utf-8-sig'))
        if payload.get('connection') != self.plan['connection']: raise ValueError('connection or build changed')
        if payload.get('symbol') != request['symbol'] or payload.get('period') != request['period']:
            raise ValueError('response scope mismatch')
        rows = payload.get('history')
        if not isinstance(rows, list) or len(rows) >= request['limit']:
            raise ValueError('missing history or possible limit truncation; no blind next-page skip')
        if payload.get('complete') is not True: raise ValueError('page completion explicitly unconfirmed')
        if any(not request['datetime_from'] <= r.get('time','') < request['datetime_to'] for r in rows):
            raise ValueError('response outside half-open request')
        audit = audit_snapshot(payload, source_id=f'page-{index:06d}',
            capture_time=captured_at, file_sha256=hashlib.sha256(raw).hexdigest(), origin='synthetic_offline_fixture')
        if audit['errors']: raise ValueError('page market-data integrity failed')
        return audit

    def run(self, source, *, now, stop=lambda: False, clock=time.monotonic, free_bytes=None):
        try:
            return self._run(source, now=now, stop=stop, clock=clock, free_bytes=free_bytes)
        except Exception:
            self.state = 'ACQUISITION_BLOCKED'
            raise

    def _run(self, source, *, now, stop, clock, free_bytes):
        validate_fixture_consent(self.consent, self.plan, now=now())
        if type(source) is not SyntheticHistorySource: raise PermissionError('only finite synthetic source accepted')
        self._load()  # Check bytes again before every explicit resume.
        self.state = 'DATASET_PARTIAL'
        started = clock()
        for index in range(len(self.receipts), len(self.requests)):
            if stop(): return self.status('interrupted_before_next_page')
            validate_fixture_consent(self.consent, self.plan, now=now())
            if index >= self.plan['max_calls']: raise ValueError('call budget exhausted')
            if self.elapsed+clock()-started >= self.plan['max_elapsed_seconds']: return self.status('cooperative_timeout')
            if free_bytes is None or free_bytes() < self.plan['min_free_disk_bytes']:
                raise OSError('free disk evidence missing or insufficient')
            request = self.requests[index]
            folder = self.root/f'page-{index:06d}'
            folder.mkdir(exist_ok=False)
            intent_bytes = _encoded(dict(request=request, plan_sha256=fingerprint(self.plan),
                consent_sha256=fingerprint(self.consent), synthetic_only=True))
            with (folder/'request.json').open('xb') as stream: stream.write(intent_bytes)
            raw = source.fetch(deepcopy(request))  # A fixture lookup; never real I/O.
            if not isinstance(raw, bytes): raise ValueError('fixture transport must return raw bytes')
            captured = now().isoformat()
            validate_fixture_consent(self.consent, self.plan, now=now())
            audit = self._inspect(raw, request, index, captured)
            # Windows are disjoint and ordered; only the other timeframe of the
            # same day can overlap. Avoid rescanning years for every daily page.
            related = [a for a in self.audits[-1:] if any(
                request['datetime_from'] <= r['time'] < request['datetime_to'] for r in a['records'])]
            collection = audit_collection([*related, audit])
            if collection['classification'] == 'invalid': raise ValueError('cross-page data conflict')
            if stop() or self.elapsed+clock()-started >= self.plan['max_elapsed_seconds']:
                return self.status('interrupted_after_response_not_committed')
            audit_bytes = _encoded(audit)
            receipt = dict(schema_version='3.3F-page-1', plan_sha256=fingerprint(self.plan),
                consent_sha256=fingerprint(self.consent), request=deepcopy(request),
                connection=deepcopy(self.plan['connection']), captured_at=captured,
                raw_sha256=hashlib.sha256(raw).hexdigest(), audit_sha256=hashlib.sha256(audit_bytes).hexdigest(),
                record_count=audit['input_rows'], returned_from=min((r['time'] for r in audit['records']), default=None),
                returned_last=max((r['time'] for r in audit['records']), default=None),
                broker_timezone=None, price_adjustments=None, corporate_events=None,
                elapsed_seconds=clock()-started,
                previous_receipt_sha256=self.receipts[-1]['receipt_sha256'] if self.receipts else None,
                synthetic_only=True, live_execution_enabled=False)
            receipt['receipt_sha256'] = fingerprint(receipt)
            receipt_bytes = _encoded(receipt)
            size = len(intent_bytes)+len(raw)+len(audit_bytes)+len(receipt_bytes)
            if self.rows+audit['input_rows'] > self.plan['max_records'] or self.storage+size > self.plan['max_storage_bytes']:
                raise ValueError('record or storage budget exhausted')
            if free_bytes() < self.plan['min_free_disk_bytes']+size: raise OSError('insufficient space before commit')
            for name, data in (('raw.json',raw), ('audit.json',audit_bytes), ('receipt.json',receipt_bytes)):
                with (folder/name).open('xb') as stream: stream.write(data)
            self.audits.append(audit); self.receipts.append(receipt)
            self.rows += audit['input_rows']; self.storage += size
            self.elapsed += receipt['elapsed_seconds']
            started = clock()
        return self.status('all_requested_fixture_pages_committed')

    def status(self, reason):
        return dict(state=self.state, reason=reason, pages_committed=len(self.receipts),
            rows=self.rows, storage_bytes=self.storage, coverage_certified=False,
            synthetic_only=True, acquisition_enabled=False, live_execution_enabled=False)


def review_acquired_dataset(collection, evidence):
    """Scoped external checks; hashes bind submitted claims, not authenticity.

    DATASET_AUDITED means data checks passed, never certification or permission
    for the Tester. A trusted real evidence reviewer remains a future requirement.
    """
    exact(evidence, {'collection_sha256','checks','sources'}, 'data review')
    if fingerprint(collection) != evidence['collection_sha256']: raise ValueError('review dataset version changed')
    exact(evidence['checks'], set(CHECKS), 'applicable data checks')
    pending = []
    if not isinstance(evidence['sources'],dict): raise ValueError('review sources required')
    for name, check in evidence['checks'].items():
        exact(check, {'status','source_sha256','limitations'}, 'scoped data check')
        sha(check['source_sha256'])
        if check['status'] not in ('pass','fail','unknown') or not isinstance(check['limitations'], list):
            raise ValueError('invalid review status')
        if check['source_sha256'] is not None:
            source = evidence['sources'].get(check['source_sha256'])
            if source is None or fingerprint(source) != check['source_sha256']:
                raise ValueError('review source missing or hash differs')
            exact(source, {'collection_sha256','check','status','limitations','details','kind'}, 'review source')
            if (source['collection_sha256'] != evidence['collection_sha256'] or source['check'] != name or
                source['status'] != check['status'] or source['limitations'] != check['limitations'] or
                source['kind'] not in ('synthetic','observed') or not isinstance(source['details'],dict)):
                raise ValueError('review source scope or interpretation differs')
        if check['status'] != 'pass' or check['source_sha256'] is None or check['limitations']: pending.append(name)
    if collection['classification'] == 'invalid': pending.append('market_data_integrity')
    if not any(s['timeframe']=='M1' for s in collection['series']): pending.append('M1_missing')
    if not any(s['timeframe']=='M5' for s in collection['series']): pending.append('M5_missing')
    if not collection['M1_M5_comparison'] or any(c['classification']!='conditional_aggregate_match' for c in collection['M1_M5_comparison']):
        pending.append('M1_M5_comparison_incomplete')
    return dict(state='DATASET_PARTIAL' if pending else 'DATASET_AUDITED',
        collection_sha256=fingerprint(collection), checks=deepcopy(evidence['checks']), blockers=pending,
        evidence_kind='synthetic' if any(s['kind']=='synthetic' for s in evidence['sources'].values()) else 'submitted_observations_not_authenticated',
        coverage_certified=False, economic_quality_verified=False, statistical_sufficiency_verified=False,
        acquisition_enabled=False, live_execution_enabled=False)


def review_session_grid(audit, calendar):
    """Compare explicit, sourced expected slots without inventing market bars.

    The supplied calendar must already encode session breaks, auctions, holidays
    and historical timezone rules. No weekday or constant-hours approximation.
    Legitimate no-trade slots require separate source evidence, never filling.
    """
    exact(calendar, {'audit_sha256','source_sha256','timezone','expected_bar_times','no_trade'}, 'session calendar')
    sha(calendar['source_sha256'])
    if fingerprint(audit) != calendar['audit_sha256']: raise ValueError('calendar audit scope changed')
    if audit['kind'] != 'bars': raise ValueError('session grid applies to bars')
    if not isinstance(calendar['expected_bar_times'],list) or not isinstance(calendar['no_trade'],dict):
        raise ValueError('explicit calendar slots and no-trade evidence required')
    step = 60 if audit['timeframe']=='M1' else 300
    stamps = calendar['expected_bar_times']
    if len(set(stamps)) != len(stamps): raise ValueError('calendar slots duplicated')
    for stamp in stamps:
        parsed = datetime.fromisoformat(stamp)
        if parsed.second or parsed.microsecond or (parsed.hour*3600+parsed.minute*60)%step:
            raise ValueError('calendar slot grid mismatch')
    for stamp, source_hash in calendar['no_trade'].items():
        sha(source_hash)
        if stamp not in stamps or source_hash is None: raise ValueError('unscoped no-trade evidence')
    observed = {r['time'] for r in audit['records']}
    missing = sorted(set(stamps)-observed)
    explained = sorted(set(missing)&set(calendar['no_trade']))
    unresolved = sorted(set(missing)-set(explained))
    blockers = []
    if audit['classification']=='invalid': blockers.append('history_integrity_invalid')
    if calendar['source_sha256'] is None: blockers.append('calendar_source_unknown')
    if calendar['timezone']=='unknown' or calendar['timezone']!=audit['timezone']:
        blockers.append('calendar_broker_timezone_unverified')
    if not stamps: blockers.append('empty_calendar_scope')
    if unresolved: blockers.append('unresolved_expected_slots')
    unexpected = sorted(observed-set(stamps))
    if unexpected: blockers.append('observations_outside_calendar_scope')
    return dict(state='DATASET_PARTIAL' if blockers else 'DATASET_AUDITED',
        unresolved_slots=unresolved, explained_no_trade_slots=explained, unexpected_slots=unexpected,
        blockers=blockers, calendar_sha256=fingerprint(calendar),
        coverage_certified=False, live_execution_enabled=False, bars_filled=0)
