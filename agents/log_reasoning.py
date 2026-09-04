"""Log's full anomaly analysis — LLM-judged, no hardcoded detection rule.

agents/log_stats.py does pure arithmetic (sums, groupbys, candidate
same-counterparty clusters) — data preparation an LLM would do unreliably
itself. Nothing in this codebase pre-decides whether a candidate cluster, a
concentration share, or a velocity burst actually *counts* as reportable —
every verdict is the model's judgment over the real evidence.

Three named, scoped categories become assessments (structuring,
concentration, velocity) — `breach` when the model judges them anomalous,
`clear` when it judges them fine, each citing the measurement fact that
carried its evidence. Anything else goes into `other_observations`:
Observation-style, unscored.
"""
from __future__ import annotations


import logging


from schemas import Assessment, EvidenceRef, Fact, Observation, Rule, typed_params
from schemas.dossier import LoadedDossier

from .llm import (
    briefing_message, format_escalation_addendum, format_reviewer_addendum, get_model,
    get_tool_call, log_cache_usage, parse_observations, system_message, THINKING_EFFORT,
    with_reasoning,
)
from .prompts import assemble
from .log_stats import (
    amount_stats,
    counterparty_breakdown,
    hourly_distribution,
    new_payee_concentration,
    structuring_clusters,
    to_dataframe,
    velocity_stats,
)

logger = logging.getLogger(__name__)

PROMPT_ID = "SPECIALIST-LOG"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective


_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "anomalous": {"type": "boolean"},
        "explanation": {"type": "string", "description": "One sentence."},
        "cited_evidence": {"type": "string", "description": "Quote the specific numbers, transaction ids, or cluster contents this judgment is based on."},
        "transaction_ids": {"type": "array", "items": {"type": "string"},
                            "description": "Exact affected transaction ids from transaction_index; empty only when anomalous=false."},
    },
    "required": ["anomalous", "explanation", "cited_evidence", "transaction_ids"],
}

_LOG_ANALYSIS_TOOL = with_reasoning({
    "name": "record_log_analysis",
    "description": "Record the structuring, concentration, and velocity judgments, plus any other open observations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "structuring": _VERDICT_SCHEMA,
            "concentration": _VERDICT_SCHEMA,
            "velocity": _VERDICT_SCHEMA,
            "other_observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "One sentence: the specific thing you noticed."},
                        "cited_evidence": {"type": "string", "description": "The exact field or value it rests on. A reference, not prose."},
                        "failure_id": {"type": ["string", "null"], "enum": ["F62", "F63", "F64", "F66", None]},
                        "transaction_ids": {"type": "array", "items": {"type": "string"},
                                            "description": "Exact affected ids from transaction_index."},
                    },
                    "required": ["note", "cited_evidence", "failure_id", "transaction_ids"],
                },
            },
        },
        "required": ["structuring", "concentration", "velocity", "other_observations"],
    },
})


def _classification(dossier: LoadedDossier) -> str | None:
    """This agent's registered classification, or None if it is not registered.

    None falls back to the ruleset's default threshold, which is the right
    behaviour: an agent the regulator has never heard of is a finding for KYA
    to make, not a reason for Log to guess at a number.
    """
    from data.registries import load_agents

    record = load_agents().get(dossier.dossier.agent_id)
    return record.get("classification") if record else None


def structured_view(dossier: LoadedDossier, structuring_rule: Rule,
                    concentration_rule: Rule | None = None) -> dict:
    """Log's canonical evidence over the whole transaction history."""
    from data.registries import load_merchants

    df = to_dataframe(dossier.transaction_history)
    params = typed_params(structuring_rule)
    new_payee_dial = (typed_params(concentration_rule).new_payee_min_share_pct
                      if concentration_rule is not None else 20.0)
    candidate_clusters = [
        c for c in structuring_clusters(df, window_hours=params.window_hours)
        if len(c["transaction_ids"]) >= params.min_cluster_size
    ]
    allowlists = [len(r.intent_mandate.authorization_scope.allowed_counterparties) for r in dossier.runs]
    return {
        "purpose_categories": sorted({r.intent_mandate.authorization_scope.purpose_category
                                      for r in dossier.runs}),
        "approved_counterparty_count": max(allowlists) if any(allowlists) else "unrestricted (category-governed)",
        # Resolved for THIS agent's classification. A threshold set beyond an
        # agent's entire operating range is not a lenient rule, it is a rule
        # switched off — and the eval would read its silence as clean
        # behaviour rather than as a dial pointing at nothing.
        "reporting_flag_threshold": params.resolve(_classification(dossier)),
        "window_hours": params.window_hours,
        "min_cluster_size": params.min_cluster_size,
        "candidate_structuring_clusters": candidate_clusters,
        "counterparty_breakdown": counterparty_breakdown(df),
        # F55's signal: who took the latest month, and whether the register
        # first saw them inside the review window.
        "latest_month_concentration": new_payee_concentration(
            df, merchants=load_merchants(),
            window_start=dossier.dossier.submission_context.executed_from),
        "new_payee_min_share_pct": new_payee_dial,
        "velocity_stats": velocity_stats(df),
        "amount_stats": amount_stats(df),
        "hourly_distribution": hourly_distribution(df),
        "transaction_index": [{
            "transaction_id": t.transaction_id,
            "run_ref": t.run_ref,
            "timestamp": t.timestamp,
            "counterparty_id": t.counterparty_id,
            "amount": t.amount,
            "currency": t.currency,
        } for t in dossier.transaction_history],
        "transaction_count": len(df),
    }


async def analyze_log(
    dossier: LoadedDossier,
    facts: list[Fact],
    structuring_rule: Rule,
    concentration_rule: Rule,
    velocity_rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    prior_observations: list[Observation] | None = None,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
    round: int = 1,
) -> tuple[list[Assessment], list[Observation]]:
    """The judged half of the Log agent. Needs a live ANTHROPIC_API_KEY
    unless `model` is supplied. `facts` are the floor's measurements; each
    verdict cites the one carrying its evidence."""
    if not dossier.transaction_history:
        return [], []

    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_LOG_ANALYSIS_TOOL],
        tool_choice={"type": "auto"},
    )

    system = system_prompt or SYSTEM_PROMPT
    if prior_observations:
        system += format_escalation_addendum(prior_observations)
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)

    response = await bound.ainvoke([
        system_message(system),
        briefing_message(context if context is not None
                         else structured_view(dossier, structuring_rule, concentration_rule)),
    ])
    log_cache_usage(response, "log")

    result = get_tool_call(response, "record_log_analysis")
    case_id = dossier.dossier.dossier_id

    def _verdict(key: str, rule: Rule) -> Assessment:
        verdict = result.get(key)
        fact_ids = [f.fact_id for f in facts if f.kind == "measurement" and f.rule_id == rule.rule_id]
        if not isinstance(verdict, dict) or "anomalous" not in verdict:
            # A malformed tool call is a judgement that did not happen, recorded
            # as such — never an exception that drops the whole specialist.
            logger.warning("Log returned a malformed %s verdict on %s: %r", key, case_id, verdict)
            return Assessment(
                assessment_id=f"{case_id}:log:{rule.rule_id}:r{round}", case_id=case_id, round=round,
                scope="case", agent="log", rule_id=rule.rule_id, fact_ids=fact_ids,
                verdict="inconclusive", confidence="possible",
                severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
                narrative=f"The model's response did not carry a usable {key} verdict; the statistics stand unjudged.",
            )
        known = {t.transaction_id: t for t in dossier.transaction_history}
        raw_ids = verdict.get("transaction_ids", [])
        transaction_ids = list(dict.fromkeys(t for t in raw_ids if t in known)) if isinstance(raw_ids, list) else []
        unknown = sorted(set(raw_ids) - set(transaction_ids)) if isinstance(raw_ids, list) else []
        if unknown:
            logger.warning("Log dropped unknown transaction ids on %s/%s: %r", case_id, key, unknown)
        anomalous = bool(verdict.get("anomalous"))
        if anomalous and not transaction_ids:
            return Assessment(
                assessment_id=f"{case_id}:log:{rule.rule_id}:r{round}", case_id=case_id, round=round,
                scope="case", agent="log", rule_id=rule.rule_id, failure_ids=[], fact_ids=fact_ids,
                verdict="inconclusive", confidence="possible",
                severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
                narrative=f"The model called {key} anomalous but named no valid affected transaction; the pattern is not projected as a failure.",
            )
        run_refs = sorted({known[t].run_ref for t in transaction_ids if known[t].run_ref})
        return Assessment(
            assessment_id=f"{case_id}:log:{rule.rule_id}:r{round}", case_id=case_id, round=round,
            scope="run" if anomalous and run_refs else "case", run_refs=run_refs,
            agent="log", rule_id=rule.rule_id, fact_ids=fact_ids,
            evidence_refs=[EvidenceRef(kind="transaction", ref=t, value=known[t].model_dump(mode="json"))
                           for t in transaction_ids],
            verdict="breach" if anomalous else "clear", confidence="probable",
            severity_floor=rule.severity_weight, severity_assessed=rule.severity_weight,
            narrative=str(verdict.get("explanation") or ""), subject=verdict.get("cited_evidence") or None,
        )

    assessments = [
        _verdict("structuring", structuring_rule),
        _verdict("concentration", concentration_rule),
        _verdict("velocity", velocity_rule),
    ]
    known = {t.transaction_id: t for t in dossier.transaction_history}
    raw_observations = []
    for item in result.get("other_observations", []):
        if not isinstance(item, dict):
            raw_observations.append(item)
            continue
        tx_ids = list(dict.fromkeys(t for t in item.get("transaction_ids", []) if t in known))
        failure_id = item.get("failure_id") if item.get("failure_id") in {"F62", "F63", "F64", "F66"} else None
        raw_observations.append({
            **item, "failure_id": failure_id, "transaction_refs": tx_ids,
            "run_refs": sorted({known[t].run_ref for t in tx_ids if known[t].run_ref}),
        })
    observations = parse_observations(raw_observations, case_id=case_id, agent="log")
    return assessments, observations
