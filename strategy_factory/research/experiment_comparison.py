"""Rank explicitly attributed offline research results."""

import json

from ..analysis import CONTEXT_FIELDS, SCENARIO_FIELDS, SCHEMA_VERSION, compare_runs


def _identity(summary):
    if not isinstance(summary, dict) or summary.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("expected a run summary with schema 1.1")
    for field in ("run_id", "local_run_id"):
        value = summary.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("invalid run identity")
    return summary.get("run_id") or summary.get("local_run_id")


def _out_of_sample(summary):
    periods = summary.get("period_results")
    if periods is None:
        return None
    if not isinstance(periods, list):
        raise ValueError("period_results must be a list or null")
    seen = set()
    result = None
    for row in periods:
        if not isinstance(row, dict) or not isinstance(row.get("period"), str):
            raise ValueError("invalid period result")
        name = row["period"]
        if not name.strip() or name in seen:
            raise ValueError("empty or duplicate period name")
        seen.add(name)
        for key in ("net_profit", "trades", "win_rate"):
            value = row.get(key)
            if value is None:
                continue
            if type(value) not in (int, float):
                raise ValueError("invalid numeric period metric")
            if key == "trades" and (value < 0 or value != int(value)):
                raise ValueError("invalid period trade count")
            if key == "win_rate" and not 0 <= value <= 100:
                raise ValueError("invalid period win rate")
        if name == "out_of_sample":
            result = {key: row.get(key) for key in ("net_profit", "trades", "win_rate")}
    return result


def _exclusion(summary, period):
    trace = summary["traceability"]
    if (summary["execution"]["status"] != "completed"
            or summary.get("status") == "source_only"
            or summary["strategy"].get("status") == "source_only"):
        return "execution_not_completed"
    if (any(summary["parameters"][key] is None for key in SCENARIO_FIELDS)
            or any(summary["data_context"][key] is None for key in CONTEXT_FIELDS)):
        return "incomplete_context"
    if (trace["classification"] != "confirmed"
            or not all(trace["readiness"][key] for key in (
                "parameters", "inputs", "cost_configuration", "history_content", "tester_settings"))
            or summary["reconciliation"]["classification"] != "verified"
            or summary["data_quality"]["classification"] != "complete"
            or summary["strategy"].get("inputs") is None):
        return "incomplete_or_unreconciled_evidence"
    for key, expected in (("use_local", True), ("use_remote", False), ("use_cloud", False)):
        if trace["tester_settings"][key]["confirmed"] is not expected:
            return "incomplete_context"
    for group, keys in (
        ("costs", ("configuration_sha256", "currency", "spread_model",
                   "commission_model", "swap_model", "fee_model")),
        ("history", ("content_sha256", "origin", "tick_source")),
        ("tester_settings", ("terminal_build",)),
    ):
        if any(trace[group][key]["status"] != "confirmed" for key in keys):
            return "incomplete_context"
    if period is None or period["net_profit"] is None or not period["trades"]:
        return "out_of_sample_result_unavailable"
    return None


def compare_experiments(summaries):
    """Return one ordered cohort when every eligible pair is comparable."""
    summaries = list(summaries)
    # Check nested fields that compare_runs does not inspect, including unused periods.
    json.dumps(summaries, allow_nan=False)
    identities = [_identity(summary) for summary in summaries]
    try:
        comparison = compare_runs(summaries)
    except OverflowError as error:
        raise ValueError("numeric summary field exceeds the comparison range") from error
    ranked = []
    excluded = {}
    for identity, summary in zip(identities, summaries):
        period = _out_of_sample(summary)
        reason = _exclusion(summary, period)
        if reason:
            excluded[identity] = reason
            continue
        ranked.append({
            "run_id": identity,
            "evidence_kind": summary["evidence_kind"],
            "out_of_sample": period,
            "promotion_eligible": False,
            "margin": None,
        })

    pairs = []
    for pair in comparison["pairs"]:
        classification, reasons = pair["classification"], pair["reasons"]
        if classification == "comparable":
            differences = [
                "different_effective_cost:" + key
                for key in ("spread_model", "commission_model", "swap_model", "fee_model")
                if pair["traceability_comparison"]["costs"][key]["classification"] == "different"
            ]
            if differences:
                classification = "not_comparable"
                reasons = sorted(reasons + differences)
        pairs.append({"run_ids": sorted((pair["left"], pair["right"])),
                      "classification": classification, "reasons": reasons})
    pairs.sort(key=lambda pair: pair["run_ids"])
    if any(pair["classification"] != "comparable"
           and all(identity not in excluded for identity in pair["run_ids"])
           for pair in pairs):
        excluded.update((row["run_id"], "incompatible_cohort") for row in ranked)
        ranked = []
    ranked.sort(key=lambda row: (-row["out_of_sample"]["net_profit"], row["run_id"]))
    return {
        "ranked": ranked,
        "criteria": [
            {"field": "out_of_sample.net_profit", "order": "descending",
             "reason": "compare reported net results for the same scenario"},
            {"field": "run_id", "order": "ascending",
             "reason": "resolve equal results independently of input order"},
        ],
        "excluded": dict(sorted(excluded.items())),
        "pairs": pairs,
        "live_execution_enabled": False,
    }
