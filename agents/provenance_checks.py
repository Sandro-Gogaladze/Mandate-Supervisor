"""Deterministic checkers for the Provenance specialist (B1).

Owns `KYA-TEC-02/05/06` — the three TEC rules answered from
`construction_context` rather than from the agent registry. The family splits
across two agents on **evidence, not topic**: an agent should never be asked a
question its own brief cannot answer. Splitting this way also removed a real
duplication, where F37 (model substitution) was assigned to Provenance in the
coverage model and would have been re-asserted by KYA.

Provenance asks one question: *was this mandate built from inputs anyone should
trust?* Everything here is per-run, because construction is a per-run event.
"""
from __future__ import annotations

from collections.abc import Callable

from data.registries import load_agents, load_model_blocklist, load_tools
from registry.loader import active_rules_by_type
from schemas import Finding, Rule, Ruleset
from schemas.dossier import LoadedDossier


class _Counter:
    def __init__(self, dossier_id: str) -> None:
        self._id, self._n = dossier_id, 0

    def next(self) -> str:
        self._n += 1
        return f"{self._id}-PRV-{self._n:03d}"


def _finding(counter: _Counter, dossier_id: str, rule: Rule, summary: str,
             details: dict | None = None) -> Finding:
    return Finding(
        finding_id=counter.next(), case_id=dossier_id, agent="provenance",
        type=rule.finding_type, rule_id=rule.rule_id,
        severity_weight=rule.severity_weight, summary=summary, details=details or {})


def _tec_02(d: LoadedDossier, rule, counter):
    """The model that answered is the model that was declared.

    Self-attested on both sides, and the data contract is explicit that this
    catches misconfiguration and silent provider upgrades rather than a
    determined liar. A mismatch is still one of the cheapest high-value checks
    in the schema: two strings the firm already logs.

    When the observed version is also blocklisted, that is said outright — a
    barred model that actually authorised payments is a different order of
    problem from one merely named on a form.
    """
    blocked = load_model_blocklist()
    offenders = []
    for r in d.runs:
        m = r.construction_context.model
        if m.declared_version != m.observed_version:
            note = " and is blocklisted" if m.observed_version in blocked else ""
            offenders.append(f"{r.run_id}: declared {m.declared_version}, "
                             f"observed {m.observed_version}{note}")
    if offenders:
        return _finding(counter, d.dossier.dossier_id, rule,
            f"{len(offenders)} run(s) were built by a model other than the one declared: "
            + "; ".join(offenders) + ".",
            details={"runs": offenders,
                     "blocklisted_observed": sorted({
                         r.construction_context.model.observed_version for r in d.runs
                         if r.construction_context.model.observed_version in blocked})})
    return None


def _tec_05(d: LoadedDossier, rule, counter):
    """The prompt is bound to a release someone actually reviewed.

    F36. The regulator holds `approved_prompt_releases`, not the operator, which
    is what makes this answerable at all: an operator asserting its own prompt
    was approved is not evidence. A run on an unlisted release executed on
    instructions that never went through review.
    """
    agent = load_agents().get(d.dossier.agent_id)
    if agent is None:
        return None
    approved = {r["release_ref"]: r for r in agent.get("approved_prompt_releases", [])}
    offenders, tampered = [], []
    for r in d.runs:
        pv = r.construction_context.policy_version
        if pv.release_ref not in approved:
            offenders.append(f"{r.run_id}: {pv.release_ref}")
        elif approved[pv.release_ref].get("prompt_hash") not in (None, pv.prompt_hash):
            # The release is approved but the bytes are not the approved bytes.
            tampered.append(f"{r.run_id}: {pv.release_ref}")
    if offenders or tampered:
        parts = []
        if offenders:
            parts.append(f"{len(offenders)} run(s) executed on an unapproved release "
                         f"({'; '.join(offenders)})")
        if tampered:
            parts.append(f"{len(tampered)} run(s) claim an approved release whose prompt hash "
                         f"does not match the approved artifact ({'; '.join(tampered)})")
        return _finding(counter, d.dossier.dossier_id, rule, "; ".join(parts) + ".",
                        details={"unapproved": offenders, "hash_mismatch": tampered,
                                 "approved_releases": sorted(approved)})
    return None


def _tec_06(d: LoadedDossier, rule, counter):
    """Every tool server used was declared and is authorised.

    Two separate failures with one shape. A server the *regulator* never
    authorised for that tool is F33. A server the *operator's own AgentCard*
    never declared is a different problem — the agent is reaching somewhere its
    own published description does not admit to — and the summary distinguishes
    them, because the supervisory response differs.

    The tool NAME in an unauthorised call is almost always one the agent may
    legitimately call. That is precisely why the server is what gets pinned.
    """
    tools = load_tools()
    card = d.dossier.agent_card
    declared = set(card.declared_tool_servers) if card else set()
    unauthorised, undeclared = [], []
    for r in d.runs:
        for tc in r.construction_context.tool_calls:
            spec = tools.get(tc.tool_name)
            if spec and tc.server_id not in spec["authorised_server_ids"]:
                unauthorised.append(f"{r.run_id}: {tc.tool_name} -> {tc.server_id}")
            elif declared and tc.server_id not in declared:
                undeclared.append(f"{r.run_id}: {tc.tool_name} -> {tc.server_id}")
    if unauthorised or undeclared:
        parts = []
        if unauthorised:
            parts.append(f"{len(unauthorised)} call(s) to a server not authorised for that tool "
                         f"({'; '.join(unauthorised)})")
        if undeclared:
            parts.append(f"{len(undeclared)} call(s) to a server the agent's own card does not "
                         f"declare ({'; '.join(undeclared)})")
        return _finding(counter, d.dossier.dossier_id, rule, "; ".join(parts) + ".",
                        details={"unauthorised": unauthorised, "undeclared": undeclared})
    return None


_PROVENANCE_CHECKERS: dict[str, Callable] = {
    "observed_model_matches_declared": _tec_02,
    "prompt_bound_to_released_artifact": _tec_05,
    "tool_servers_declared": _tec_06,
}

# The rules Provenance owns out of the KYA rulebook. KYA runs the other 39, and
# this split is on evidence rather than topic — see kya-ruleset.md Part 3.5.
PROVENANCE_RULE_TYPES = frozenset(_PROVENANCE_CHECKERS)


def run_provenance_checks(dossier: LoadedDossier, ruleset: Ruleset) -> list[Finding]:
    counter = _Counter(dossier.dossier.dossier_id)
    findings: list[Finding] = []
    for rule_type, rule in active_rules_by_type(ruleset).items():
        if rule_type not in PROVENANCE_RULE_TYPES:
            continue
        if (f := _PROVENANCE_CHECKERS[rule_type](dossier, rule, counter)) is not None:
            findings.append(f)
    return findings
