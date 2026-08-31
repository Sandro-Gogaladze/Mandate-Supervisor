"""The agent→allowed-tools map and the tools themselves (architecture-v2 §16).

This is what makes the concept note's "tool access is dispatcher-permissioned,
not prompt-instructed" true about the code: before this module there was no
permission map because there were no tools — every `_*_TOOL` in agents/ is an
output-schema constraint, not a capability. The investigator changes that,
and the map becomes real.

Every tool here is **read-only, deterministic, and non-LLM**. No tool writes
to the ledger, mutates a ruleset, or makes a model call. None returns
`line_items[].description` — the one adversarial field in the schema
(case-007's injection lives there); transaction rows are structured, and the
injection surface stays closed. Where a result does contain firm-authored
strings (counterparty names, firm names), they are delimited exactly as
agents/mandate_reasoning.py delimits merchant text.

`tools_for()` is the only way any agent obtains a tool definition, and
`execute_tool()` re-checks the map on every call — permissioning enforced at
both ends, in code.
"""
from __future__ import annotations

import json
from datetime import date

from data.canonical import sha256_hex
from data.issuers import load_issuer_registry
from ingestion.normalize import IngestedCase
from ledger import LedgerStore
from registry.loader import (
    load_drift_ruleset,
    load_kya_ruleset,
    load_log_ruleset,
    load_mandate_ruleset,
)

AGENT_TOOLS: dict[str, frozenset[str]] = {
    "investigator": frozenset({
        "get_transactions",
        "get_counterparty_profile",
        "get_issuer_record",
        "get_rule",
        "recompute_stats",
        "get_case_findings",
    }),
    # Schema-constrained output only — no callable capabilities, by design:
    # the specialists judge the evidence they are briefed with; they do not
    # go looking for more.
    "mandate": frozenset(),
    "kya": frozenset(),
    "log": frozenset(),
    "drift": frozenset(),
    "drafting": frozenset(),
    "orchestrator": frozenset(),
    "synthesizer": frozenset(),
}


class UnknownAgentError(KeyError):
    pass


class ToolNotPermittedError(PermissionError):
    pass


def _delimit(text: str) -> str:
    return f"<<<UNTRUSTED_FIRM_TEXT>>>{text}<<<END_UNTRUSTED_FIRM_TEXT>>>"


def result_digest(result) -> str:
    """sha256 of the canonical result JSON — what ToolCallRecord stores so
    the audit trail can prove what a tool returned without storing every
    (possibly large) body."""
    blob = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{sha256_hex(blob.encode('utf-8'))}"


# ---------------------------------------------------------------------------
# Tool schemas (what the model sees)
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS: dict[str, dict] = {
    "get_transactions": {
        "name": "get_transactions",
        "description": "Rows from THIS case's settled transaction history, optionally filtered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "counterparty_id": {"type": "string"},
                "date_from": {"type": "string", "description": "ISO date, inclusive"},
                "date_to": {"type": "string", "description": "ISO date, inclusive"},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
            },
        },
    },
    "get_counterparty_profile": {
        "name": "get_counterparty_profile",
        "description": (
            "Aggregate profile of one counterparty: count, total, share, first/last "
            "seen, MCCs in this case — plus every OTHER case in the ledger where the "
            "same counterparty_id appears."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"counterparty_id": {"type": "string"}},
            "required": ["counterparty_id"],
        },
    },
    "get_issuer_record": {
        "name": "get_issuer_record",
        "description": "The issuer trust-registry record for an issuer_id, or its absence.",
        "input_schema": {
            "type": "object",
            "properties": {"issuer_id": {"type": "string"}},
            "required": ["issuer_id"],
        },
    },
    "get_rule": {
        "name": "get_rule",
        "description": "What a registry rule actually checks: type, status, params, severity, description.",
        "input_schema": {
            "type": "object",
            "properties": {"rule_id": {"type": "string", "description": "e.g. LOG-STR-01"}},
            "required": ["rule_id"],
        },
    },
    "recompute_stats": {
        "name": "recompute_stats",
        "description": (
            "Re-run the deterministic statistics with different parameters: "
            "kind 'log' (structuring clusters/velocity, param window_hours) or "
            "kind 'drift' (baseline split/PSI/z-score, param baseline_window_days)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["log", "drift"]},
                "window_hours": {"type": "number"},
                "baseline_window_days": {"type": "number"},
            },
            "required": ["kind"],
        },
    },
    "get_case_findings": {
        "name": "get_case_findings",
        "description": "What is already on this case's record: findings and observations.",
        "input_schema": {"type": "object", "properties": {}},
    },
}


def tools_for(agent_name: str) -> list[dict]:
    """The only way any agent obtains a tool definition. Raises on an
    unregistered agent rather than defaulting to an empty (or full) set —
    an unknown agent asking for tools is a wiring bug, not a preference."""
    if agent_name not in AGENT_TOOLS:
        raise UnknownAgentError(
            f"agent {agent_name!r} is not in AGENT_TOOLS — every agent must be "
            f"registered explicitly, with an empty set if it gets no tools"
        )
    return [_TOOL_SCHEMAS[name] for name in sorted(AGENT_TOOLS[agent_name])]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _tx_row(t) -> dict:
    row = t.model_dump()
    row["counterparty_name"] = _delimit(row["counterparty_name"])
    return row


def _get_transactions(case: IngestedCase, store, args: dict):
    rows = case.case.transaction_history
    if cid := args.get("counterparty_id"):
        rows = [t for t in rows if t.counterparty_id == cid]
    if date_from := args.get("date_from"):
        rows = [t for t in rows if date.fromisoformat(t.timestamp[:10]) >= date.fromisoformat(date_from[:10])]
    if date_to := args.get("date_to"):
        rows = [t for t in rows if date.fromisoformat(t.timestamp[:10]) <= date.fromisoformat(date_to[:10])]
    if (lo := args.get("min_amount")) is not None:
        rows = [t for t in rows if t.amount >= lo]
    if (hi := args.get("max_amount")) is not None:
        rows = [t for t in rows if t.amount <= hi]
    return {"count": len(rows), "transactions": [_tx_row(t) for t in rows]}


def _get_counterparty_profile(case: IngestedCase, store: LedgerStore | None, args: dict):
    cid = args["counterparty_id"]
    mine = [t for t in case.case.transaction_history if t.counterparty_id == cid]
    total_all = sum(t.amount for t in case.case.transaction_history) or 1.0
    profile = {
        "counterparty_id": cid,
        "this_case": {
            "transaction_count": len(mine),
            "total": round(sum(t.amount for t in mine), 2),
            "share_of_spend": round(sum(t.amount for t in mine) / total_all, 4),
            "first_seen": min((t.timestamp for t in mine), default=None),
            "last_seen": max((t.timestamp for t in mine), default=None),
            "mccs": sorted({t.mcc for t in mine}),
            "names_used": sorted({_delimit(t.counterparty_name) for t in mine}),
        },
        "other_cases": [],
    }
    if store is not None:
        for other_id in store.all_case_ids():
            if other_id == case.case.case_id:
                continue
            submissions = [e for e in store.events_for(other_id) if e.event_type == "case_submitted"]
            if not submissions:
                continue
            raw = submissions[-1].payload
            hits = [t for t in raw.get("transaction_history", []) if t.get("counterparty_id") == cid]
            if hits:
                profile["other_cases"].append({
                    "case_id": other_id,
                    "firm": _delimit((raw.get("firm") or {}).get("name", "unknown")),
                    "transaction_count": len(hits),
                    "total": round(sum(t.get("amount", 0.0) for t in hits), 2),
                })
    return profile


def _get_issuer_record(case: IngestedCase, store, args: dict):
    issuer_id = args["issuer_id"]
    registry = load_issuer_registry()
    record = registry.get(issuer_id)
    if record is None:
        return {
            "issuer_id": issuer_id, "present_in_trust_registry": False,
            "note": "Absent entirely — never accredited; distinct from (and at least as severe as) an explicit revocation.",
        }
    return {"present_in_trust_registry": True, **record}


def _get_rule(case: IngestedCase, store, args: dict):
    rule_id = args["rule_id"]
    for loader in (load_kya_ruleset, load_mandate_ruleset, load_log_ruleset, load_drift_ruleset):
        ruleset = loader()
        for rule in ruleset.rules:
            if rule.rule_id == rule_id:
                return {"ruleset": ruleset.ruleset_id, **rule.model_dump()}
    return {"rule_id": rule_id, "found": False, "note": "No such rule in any registry ruleset."}


def _recompute_stats(case: IngestedCase, store, args: dict):
    from agents import drift_stats, log_stats

    df = log_stats.to_dataframe(case.case.transaction_history)
    if args["kind"] == "log":
        window = float(args.get("window_hours", 24.0))
        return {
            "window_hours": window,
            "structuring_clusters": log_stats.structuring_clusters(df, window_hours=window),
            "velocity_stats": log_stats.velocity_stats(df),
            "amount_stats": log_stats.amount_stats(df),
        }
    window_days = float(args.get("baseline_window_days", 30))
    baseline, comparison = drift_stats.split_baseline(df, baseline_window_days=window_days)
    if baseline.empty or comparison.empty:
        return {
            "baseline_window_days": window_days,
            "note": "One of the windows is empty at this split — no comparison possible.",
            "baseline_count": len(baseline), "comparison_count": len(comparison),
        }
    return {
        "baseline_window_days": window_days,
        "baseline_count": len(baseline),
        "comparison_count": len(comparison),
        "amount_shift": drift_stats.amount_shift(baseline, comparison),
        "frequency_shift": drift_stats.frequency_shift(baseline, comparison),
        "counterparty_mix_psi": drift_stats.distribution_psi(baseline, comparison, "counterparty_id"),
        "mcc_mix_psi": drift_stats.distribution_psi(baseline, comparison, "mcc"),
    }


def _get_case_findings(case: IngestedCase, store: LedgerStore | None, args: dict):
    if store is None or not store.has_case(case.case.case_id):
        return {"findings": [], "observations": [], "note": "No record in the ledger yet."}
    from ledger.projection import project_case

    record = project_case(store.events_for(case.case.case_id))
    return {
        "findings": [
            {"finding_id": f.finding_id, "agent": f.agent, "type": f.type,
             "rule_id": f.rule_id, "summary": f.summary}
            for f in record.findings
        ],
        "observations": [
            {"agent": o.agent, "note": o.note, "cited_evidence": o.cited_evidence}
            for o in record.observations
        ],
    }


_IMPLEMENTATIONS = {
    "get_transactions": _get_transactions,
    "get_counterparty_profile": _get_counterparty_profile,
    "get_issuer_record": _get_issuer_record,
    "get_rule": _get_rule,
    "recompute_stats": _recompute_stats,
    "get_case_findings": _get_case_findings,
}


def execute_tool(
    agent_name: str,
    tool_name: str,
    arguments: dict,
    *,
    case: IngestedCase,
    store: LedgerStore | None = None,
):
    """Executes one permitted tool call. The map is re-checked here — even
    code that somehow bound a tool it shouldn't have cannot execute it."""
    if agent_name not in AGENT_TOOLS:
        raise UnknownAgentError(f"agent {agent_name!r} is not registered in AGENT_TOOLS")
    if tool_name not in AGENT_TOOLS[agent_name]:
        raise ToolNotPermittedError(
            f"agent {agent_name!r} is not permitted to call {tool_name!r} "
            f"(allowed: {sorted(AGENT_TOOLS[agent_name])})"
        )
    return _IMPLEMENTATIONS[tool_name](case, store, arguments or {})
