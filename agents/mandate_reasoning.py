"""Mandate's one contained model call — per-line-item intent fidelity against
the shopper's own sentence, over the whole dossier (HANDOFF §5.1).

`MND-SEM-01`, and the only source of F49: *technically within the rules, but
not what the person meant.* Checking a cart against a three-month envelope
is nearly vacuous; checking it against "vitamin c serum, around $50" is not,
which is why the mandate lives on the run and why this call exists.

One call, every run that reached a cart, a verdict per run. Code does the
enforcing: every `run_id` the model returns must be one it was shown (an
invented id is dropped and logged), a run it did not judge is recorded as
`inconclusive` rather than silently passed, the consistent runs roll into
one `clear` assessment citing them all, and each mismatch is its own
`breach` citing the run and the measurement the floor recorded for it. An
assessment about run-level behaviour that names no run cannot exist here.

Two fields are firm-authored free text and reach the model delimited:
line-item descriptions (merchant-written, the injection surface) and the
agent's own attestation. The system prompt says they are data. This is
deliberately independent of agents/mandate_checks.py's line-item injection
heuristic — two mechanisms, so a manipulated semantic check does not leave
injection detection with a single point of failure.
"""
from __future__ import annotations

import logging


from schemas import Assessment, Fact, Observation, Rule
from schemas.dossier import LoadedDossier

from .llm import (
    briefing_message, format_reviewer_addendum, get_model, get_tool_call, log_cache_usage,
    parse_observations, system_message, THINKING_EFFORT, with_reasoning,
)
from .prompts import assemble

logger = logging.getLogger(__name__)

PROMPT_ID = "SPECIALIST-MANDATE"
SYSTEM_PROMPT = assemble(PROMPT_ID).effective

_FIDELITY_TOOL = with_reasoning({
    "name": "record_intent_fidelity",
    "description": "Record, for every run shown, whether the cart answers what the shopper asked for.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "Exactly as shown; never invented."},
                        "consistent": {"type": "boolean"},
                        "quoted_evidence": {
                            "type": "string",
                            "description": "If not consistent: the exact text (from the cart or the agent's reasoning) that shows the mismatch. Empty string if consistent.",
                        },
                        "explanation": {"type": "string", "description": "One short sentence. Omit reasoning that repeats the quoted evidence."},
                    },
                    "required": ["run_id", "consistent", "quoted_evidence", "explanation"],
                },
            },
            "other_observations": {
                "type": "array",
                "description": (
                    "Anything worth a supervisor's attention that no verdict above captures "
                    "and no rule covers. Empty when there is nothing."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "One sentence: the specific thing you noticed."},
                        "cited_evidence": {"type": "string",
                                           "description": "The exact field, SKU or quoted text it rests on. A reference, not prose."},
                        "run_refs": {"type": "array", "items": {"type": "string"},
                                     "description": "Exact run_ids from the runs shown; never invented."},
                    },
                    "required": ["note", "cited_evidence", "run_refs"],
                },
            },
        },
        "required": ["verdicts", "other_observations"],
    },
})


def _delimit(kind: str, text: str) -> str:
    return f"<<<UNTRUSTED_{kind}_TEXT>>>{text}<<<END_UNTRUSTED_{kind}_TEXT>>>"


def structured_view(dossier: LoadedDossier, floor_facts: list[Fact]) -> dict:
    """Mandate's canonical evidence: every run that reached a cart, as the
    shopper's signed sentence against what was bought, plus what the floor
    established by rule. Fifty runs' worth of pairs, not fifty JSON files."""
    by_rule: dict[str, dict[str, int]] = {}
    for f in floor_facts:
        if f.rule_id and f.kind != "measurement":
            by_rule.setdefault(f.rule_id, {})
            by_rule[f.rule_id][f.kind] = by_rule[f.rule_id].get(f.kind, 0) + 1
    runs = []
    for r in dossier.runs:
        if r.cart is None:
            continue
        runs.append({
            "run_id": r.run_id,
            "outcome": r.outcome,
            "shopper_request": r.intent_mandate.natural_language_intent,
            "purpose_category": r.intent_mandate.authorization_scope.purpose_category,
            "max_transaction_amount": r.intent_mandate.authorization_scope.max_transaction_amount,
            "merchant": r.cart.merchant.name,
            "cart_total": r.cart.cart_total,
            "currency": r.cart.currency,
            "line_items": [
                {"sku": li.sku, "qty": li.qty, "unit_price": li.unit_price,
                 "description": _delimit("MERCHANT", li.description)}
                for li in r.cart.line_items
            ],
            "agent_reasoning": _delimit("AGENT", r.cart.agent_attestation.reasoning),
        })
    return {
        "dossier_id": dossier.dossier.dossier_id,
        "runs_with_a_cart": len(runs),
        "runs": runs,
        "rule_outcomes": by_rule,
        "floor_breaches": [{"rule_id": f.rule_id, "run_id": f.run_ref, "statement": f.statement}
                           for f in floor_facts if f.kind == "breach"],
    }


async def check_intent_fidelity(
    dossier: LoadedDossier,
    facts: list[Fact],
    rule: Rule,
    *,
    model=None,
    thinking_effort: str = THINKING_EFFORT,
    reviewer_directive: str | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
    round: int = 1,
) -> tuple[list[Assessment], list[Observation]]:
    """The whole-dossier fidelity judgement. Needs a live ANTHROPIC_API_KEY
    unless `model` is supplied. `facts` are the floor's; each verdict cites
    the `MND-SEM-01` measurement the floor recorded for that run."""
    case_id = dossier.dossier.dossier_id
    shown = [r.run_id for r in dossier.runs if r.cart is not None]
    if not shown:
        return [], []
    measurements = {f.run_ref: f for f in facts
                    if f.kind == "measurement" and f.rule_id == rule.rule_id and f.run_ref}

    model = model or get_model()
    bound = model.bind(
        output_config={"effort": thinking_effort},
        tools=[_FIDELITY_TOOL],
        tool_choice={"type": "auto"},
    )
    system = system_prompt or SYSTEM_PROMPT
    if reviewer_directive:
        system += format_reviewer_addendum(reviewer_directive)
    response = await bound.ainvoke([
        system_message(system),
        briefing_message(context if context is not None else structured_view(dossier, facts)),
    ])
    log_cache_usage(response, "mandate")
    result = get_tool_call(response, "record_intent_fidelity")

    verdicts: dict[str, dict] = {}
    for v in result.get("verdicts", []):
        if not isinstance(v, dict) or "run_id" not in v or "consistent" not in v:
            logger.warning("Mandate fidelity: skipping malformed verdict for %s: %r", case_id, v)
            continue
        if v["run_id"] not in shown:
            # The mechanical "cannot invent" rule: a run the model was not
            # shown does not exist for it.
            logger.warning("Mandate fidelity: dropping verdict for unknown run %r on %s", v["run_id"], case_id)
            continue
        verdicts[v["run_id"]] = v

    def _fact_ids(run_ids: list[str]) -> list[str]:
        return [measurements[r].fact_id for r in run_ids if r in measurements]

    common = dict(case_id=case_id, round=round, scope="run", agent="mandate", rule_id=rule.rule_id,
                  confidence="probable", severity_floor=rule.severity_weight,
                  severity_assessed=rule.severity_weight)
    out: list[Assessment] = []
    for run_id in shown:
        v = verdicts.get(run_id)
        if v is not None and not v["consistent"]:
            out.append(Assessment(
                assessment_id=f"{case_id}:mandate:{rule.rule_id}:{run_id}:r{round}",
                verdict="breach", fact_ids=_fact_ids([run_id]), run_refs=[run_id],
                subject=(v.get("quoted_evidence") or None),
                narrative=f"{run_id}: {v.get('explanation', '')}".strip(), **common))
    consistent = [r for r in shown if r in verdicts and verdicts[r]["consistent"]]
    if consistent:
        out.append(Assessment(
            assessment_id=f"{case_id}:mandate:{rule.rule_id}:r{round}",
            verdict="clear", fact_ids=_fact_ids(consistent), run_refs=consistent,
            narrative=(f"{len(consistent)} of {len(shown)} run(s) judged consistent with what the "
                       f"shopper asked for."), **common))
    unjudged = [r for r in shown if r not in verdicts]
    if unjudged:
        out.append(Assessment(
            assessment_id=f"{case_id}:mandate:{rule.rule_id}:inconclusive:r{round}",
            verdict="inconclusive", fact_ids=_fact_ids(unjudged), run_refs=unjudged,
            narrative=(f"{len(unjudged)} run(s) shown to the model received no verdict: "
                       f"{', '.join(unjudged[:5])}{' …' if len(unjudged) > 5 else ''}."), **common))

    # The open channel. Same mechanical rule as the verdicts: a run the model
    # was not shown does not exist for it. An observation carries no rule_id
    # and no severity, so nothing here can reach the score — which is what
    # makes open-ended hunting safe to allow at all.
    raw_observations = []
    for item in result.get("other_observations", []):
        if not isinstance(item, dict):
            raw_observations.append(item)
            continue
        refs = [r for r in item.get("run_refs", []) if r in shown] if isinstance(item.get("run_refs"), list) else []
        dropped = sorted(set(item.get("run_refs", [])) - set(refs)) if isinstance(item.get("run_refs"), list) else []
        if dropped:
            logger.warning("Mandate: dropping unknown run refs on an observation for %s: %r", case_id, dropped)
        raw_observations.append({**item, "run_refs": refs})
    observations = parse_observations(raw_observations, case_id=case_id, agent="mandate")
    return out, observations
