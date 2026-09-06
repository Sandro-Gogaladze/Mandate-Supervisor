"""Drift's LLM judgment — no hardcoded threshold decides whether a
statistical shift counts as drift, same design as agents/log_reasoning.py.

agents/drift_stats.py computes real PSI/z-score/frequency statistics
between a baseline window and everything after it. What it doesn't do is
decide whether the shift is *meaningful* drift versus legitimate seasonal
or business-growth variation. That judgment is the model's, and it becomes
a `breach` or `clear` assessment citing the measurement it was shown.
"""
from __future__ import annotations

import logging


from schemas import Assessment, EvidenceRef, Fact, Observation, Rule, typed_params
from schemas.dossier import LoadedDossier

from .drift_stats import amount_shift, change_points, distribution_psi, frequency_shift, mix_breakdown, split_baseline, to_dataframe
from .llm import (
    briefing_message, format_escalation_addendum, format_reviewer_addendum, get_model,
    get_tool_call, log_cache_usage, parse_observations, system_message, THINKING_EFFORT,
    with_reasoning,
)
from .prompts import assemble

logger = logging.getLogger(__name__)

PROMPT_ID = "SPECIALIST-DRIFT"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective


_DRIFT_ANALYSIS_TOOL = with_reasoning({
    "name": "record_drift_analysis",
    "description": "Record the drift judgment, plus any other open observations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "drift": {
                "type": "object",
                "properties": {
                    "anomalous": {"type": "boolean"},
                    "explanation": {"type": "string", "description": "One sentence."},
                    "cited_evidence": {"type": "string", "description": "Quote the specific PSI/z-score/frequency numbers this judgment is based on."},
                    "transaction_ids": {"type": "array", "items": {"type": "string"},
                                        "description": "Exact comparison-period transactions affected by the drift; empty only when anomalous=false."},
                    "onset_event_ref": {
                        "type": ["string", "null"],
                        "description": "If drift is present: the change_points entry (its exact ref) the onset most plausibly lands on; null if none fits.",
                    },
                },
                "required": ["anomalous", "explanation", "cited_evidence", "transaction_ids", "onset_event_ref"],
            },
            "other_observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "One sentence: the specific thing you noticed."},
                        "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."},
                    },
                    "required": ["note", "cited_evidence"],
                },
            },
        },
        "required": ["drift", "other_observations"],
    },
})


def structured_view(dossier: LoadedDossier, drift_rule: Rule) -> dict:
    """Drift's canonical evidence over the whole transaction history."""
    df = to_dataframe(dossier.transaction_history)
    params = typed_params(drift_rule)
    baseline, comparison = split_baseline(df, baseline_window_days=params.baseline_window_days)
    return {
        "purpose_categories": sorted({r.intent_mandate.authorization_scope.purpose_category
                                      for r in dossier.runs}),
        "baseline_window_days": params.baseline_window_days,
        "baseline_transaction_count": len(baseline),
        "comparison_transaction_count": len(comparison),
        "amount_shift": amount_shift(baseline, comparison),
        "frequency_shift": frequency_shift(baseline, comparison),
        "counterparty_mix_psi": distribution_psi(baseline, comparison, "counterparty_id"),
        "mcc_mix_psi": distribution_psi(baseline, comparison, "mcc"),
        "baseline_counterparty_mix": mix_breakdown(baseline, "counterparty_id"),
        "comparison_counterparty_mix": mix_breakdown(comparison, "counterparty_id"),
        "baseline_mcc_mix": mix_breakdown(baseline, "mcc"),
        "comparison_mcc_mix": mix_breakdown(comparison, "mcc"),
        # F65 — the same statistics before and after each dated change the
        # operator logged, so an onset can land on a named event.
        "change_points": change_points(df, [c.model_dump() for c in dossier.dossier.change_log]),
        "transaction_index": [{
            "transaction_id": t.transaction_id, "run_ref": t.run_ref,
            "timestamp": t.timestamp, "counterparty_id": t.counterparty_id,
            "mcc": t.mcc, "amount": t.amount, "currency": t.currency,
        } for t in dossier.transaction_history],
    }


async def analyze_drift(
    dossier: LoadedDossier,
    facts: list[Fact],
    drift_rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
    ruleset=None,
    round: int = 1,
) -> tuple[list[Assessment], list[Observation]]:
    """Needs a live ANTHROPIC_API_KEY unless `model` is supplied. Caller
    (agents/drift.py) is responsible for the insufficient_baseline gate."""
    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_DRIFT_ANALYSIS_TOOL],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        system_message(system),
        briefing_message(context if context is not None else structured_view(dossier, drift_rule)),
    ])
    log_cache_usage(response, "drift")

    result = get_tool_call(response, "record_drift_analysis")
    case_id = dossier.dossier.dossier_id
    measurement = next((f for f in facts if f.kind == "measurement" and f.rule_id == drift_rule.rule_id), None)
    verdict = result.get("drift")
    events = {c.ref: c for c in dossier.dossier.change_log}
    if not isinstance(verdict, dict) or "anomalous" not in verdict:
        # A malformed tool call is a judgement that did not happen, recorded
        # as such — never an exception that drops the whole specialist.
        logger.warning("Drift returned a malformed verdict on %s: %r", case_id, verdict)
        return [Assessment(
            assessment_id=f"{case_id}:drift:{drift_rule.rule_id}:r{round}", case_id=case_id, round=round,
            scope="case", agent="drift", rule_id=drift_rule.rule_id,
            fact_ids=[measurement.fact_id] if measurement else [], verdict="inconclusive", confidence="possible",
            severity_floor=drift_rule.severity_weight, severity_assessed=drift_rule.severity_weight,
            narrative="The model's response did not carry a usable drift verdict; the statistics stand unjudged.",
        )], parse_observations(result.get("other_observations", []), case_id=case_id, agent="drift")
    onset = verdict.get("onset_event_ref")
    if onset is not None and onset not in events:
        # The mechanical "cannot invent" rule: an onset must be an event the
        # operator actually logged.
        logger.warning("Drift named an onset event not in the change_log for %s: %r", case_id, onset)
        onset = None
    known = {t.transaction_id: t for t in dossier.transaction_history}
    raw_ids = verdict.get("transaction_ids", [])
    transaction_ids = list(dict.fromkeys(t for t in raw_ids if t in known)) if isinstance(raw_ids, list) else []
    unknown = sorted(set(raw_ids) - set(transaction_ids)) if isinstance(raw_ids, list) else []
    if unknown:
        logger.warning("Drift dropped unknown transaction ids on %s: %r", case_id, unknown)
    anomalous = bool(verdict.get("anomalous"))
    if anomalous and not transaction_ids:
        return [Assessment(
            assessment_id=f"{case_id}:drift:{drift_rule.rule_id}:r{round}", case_id=case_id, round=round,
            scope="case", agent="drift", rule_id=drift_rule.rule_id, failure_ids=[],
            fact_ids=[measurement.fact_id] if measurement else [], verdict="inconclusive", confidence="possible",
            severity_floor=drift_rule.severity_weight, severity_assessed=drift_rule.severity_weight,
            narrative="The model called drift anomalous but named no valid affected transaction; the pattern is not projected as F65.",
        )], parse_observations(result.get("other_observations", []), case_id=case_id, agent="drift")
    run_refs = sorted({known[t].run_ref for t in transaction_ids if known[t].run_ref})
    assessment = Assessment(
        assessment_id=f"{case_id}:drift:{drift_rule.rule_id}:r{round}", case_id=case_id, round=round,
        scope="run" if anomalous and run_refs else "case", run_refs=run_refs,
        agent="drift", rule_id=drift_rule.rule_id,
        failure_ids=["F65"] if anomalous and onset else ([] if anomalous else None),
        fact_ids=[measurement.fact_id] if measurement else [],
        evidence_refs=([EvidenceRef(kind="field", ref=f"change_log[{onset}]",
                                    value=events[onset].at)] if onset else [])
                      + [EvidenceRef(kind="transaction", ref=t, value=known[t].model_dump(mode="json"))
                         for t in transaction_ids],
        verdict="breach" if anomalous else "clear", confidence="probable",
        severity_floor=drift_rule.severity_weight, severity_assessed=drift_rule.severity_weight,
        narrative=str(verdict.get("explanation") or "") + (f" Onset: {onset} ({events[onset].kind}, "
                                            f"{events[onset].at[:10]})." if onset else ""),
        subject=onset or (verdict.get("cited_evidence") or None),
    )
    out = [assessment]
    # DRIFT-UNX-01 — behaviour shifted and the operator's own change log
    # accounts for none of it. Judged, because its first half IS the verdict
    # above: with no model there is no drift to be unexplained. Recorded only
    # when the rule is in force, so retiring it in the sandbox stops it.
    unexplained = next((r for r in (ruleset.rules if ruleset else [])
                        if r.type == "drift_has_no_logged_cause" and r.status == "active"), None)
    if unexplained is not None and anomalous:
        out.append(Assessment(
            assessment_id=f"{case_id}:drift:{unexplained.rule_id}:r{round}", case_id=case_id,
            round=round, scope="run" if run_refs else "case", run_refs=run_refs,
            agent="drift", rule_id=unexplained.rule_id,
            failure_ids=["F89"] if onset is None else [],
            fact_ids=[measurement.fact_id] if measurement else [],
            verdict="breach" if onset is None else "clear", confidence="probable",
            severity_floor=unexplained.severity_weight, severity_assessed=unexplained.severity_weight,
            narrative=("The change log offers no event that accounts for this shift."
                       if onset is None else
                       f"The shift is accounted for by {onset} ({events[onset].kind}, "
                       f"{events[onset].at[:10]})."),
            subject=onset))
    observations = parse_observations(result.get("other_observations", []), case_id=case_id, agent="drift")
    return out, observations
