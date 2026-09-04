"""Deterministic checkers for the Provenance specialist (B1).

Reads `provenance.json`: the three TEC rules answered from
`construction_context` (moved here from the KYA book with their ids kept —
the family splits across two agents on **evidence, not topic**), the
card-versus-credential rule, and the measurement behind the judged
reconciliation of the four sources that should agree: the agent card, the
credential, the register, and the tool calls actually observed.

Provenance asks one question: *was this mandate built from inputs anyone should
trust?* The construction rules are run-level — construction is a per-run event
— so each produces one fact per run; the card and the reconciliation are
properties of the dossier.
"""
from __future__ import annotations

from dataclasses import dataclass

from data.registries import load_agents, load_model_blocklist, load_tools
from schemas import EvidenceRef, Fact, FactBuilder, Rule, Ruleset
from schemas.dossier import LoadedDossier, Run

from .facts import evaluate_ruleset

DOMAIN = "provenance"


@dataclass
class ProvenanceContext:
    fb: FactBuilder
    agent_id: str
    agent: dict | None             # the register entry for the agent under review
    tools: dict[str, dict]         # tool_name -> {authorised_server_ids, ...}
    blocklist: dict[str, dict]
    declared_servers: set[str] | None   # from the agent card; None when no card was filed
    card: object = None
    credential_capabilities: list[str] = None  # type: ignore[assignment]
    runs: list = None  # type: ignore[assignment]
    deployment_target: dict = None  # type: ignore[assignment]


def build_context(d: LoadedDossier, *, agents: dict | None = None, tools: dict | None = None,
                  blocklist: dict | None = None) -> ProvenanceContext:
    """Registries are injectable so the sandbox and the tests can run the same
    checkers against a different regulator-side state."""
    agents = agents if agents is not None else load_agents()
    card = d.dossier.agent_card
    return ProvenanceContext(
        fb=FactBuilder(d.dossier.dossier_id, DOMAIN),
        agent_id=d.dossier.agent_id,
        agent=agents.get(d.dossier.agent_id),
        tools=tools if tools is not None else load_tools(),
        blocklist=blocklist if blocklist is not None else load_model_blocklist(),
        declared_servers=set(card.declared_tool_servers) if card else None,
        card=card, credential_capabilities=list(d.dossier.kya_credential.capabilities),
        runs=list(d.runs), deployment_target=d.dossier.submission_context.deployment_target.model_dump(),
    )


def _tec_02(rule: Rule, run: Run, ctx: ProvenanceContext) -> Fact:
    """The model that answered is the model that was declared.

    Self-attested on both sides, and the data contract is explicit that this
    catches misconfiguration and silent provider upgrades rather than a
    determined liar. A mismatch is still one of the cheapest high-value checks
    in the schema: two strings the firm already logs.

    When the observed version is also blocklisted, that is said outright — a
    barred model that actually authorised payments is a different order of
    problem from one merely named on a form.
    """
    m = run.construction_context.model
    refs = [EvidenceRef(kind="field", ref="construction_context.model.declared_version",
                        value=m.declared_version),
            EvidenceRef(kind="field", ref="construction_context.model.observed_version",
                        value=m.observed_version)]
    blocked = m.observed_version in ctx.blocklist
    values = {"declared_version": m.declared_version, "observed_version": m.observed_version,
              "observed_blocklisted": blocked}
    if m.declared_version != m.observed_version:
        return ctx.fb.breach(
            rule, f"{run.run_id} was built by {m.observed_version}, not the declared "
                  f"{m.declared_version}" + (", and the observed model is blocklisted." if blocked
                                             else "."),
            run_ref=run.run_id, values=values, refs=refs)
    return ctx.fb.satisfied(
        rule, f"{run.run_id}: the observed model {m.observed_version} is the declared one.",
        run_ref=run.run_id, values=values, refs=refs)


def _tec_05(rule: Rule, run: Run, ctx: ProvenanceContext) -> Fact:
    """The prompt is bound to a release someone actually reviewed.

    F36. The regulator holds `approved_prompt_releases`, not the operator, which
    is what makes this answerable at all: an operator asserting its own prompt
    was approved is not evidence. A run on an unlisted release executed on
    instructions that never went through review.
    """
    pv = run.construction_context.policy_version
    refs = [EvidenceRef(kind="field", ref="construction_context.policy_version.release_ref",
                        value=pv.release_ref),
            EvidenceRef(kind="field", ref="construction_context.policy_version.prompt_hash",
                        value=pv.prompt_hash)]
    if ctx.agent is None:
        return ctx.fb.absent(
            rule, "no_registry_record",
            f"{run.run_id}: {ctx.agent_id} has no entry in the agent register, so no approved "
            f"prompt release exists to check {pv.release_ref} against.",
            missing=f"registry:agents[{ctx.agent_id}]", run_ref=run.run_id)
    approved = {r["release_ref"]: r for r in ctx.agent.get("approved_prompt_releases", [])}
    values = {"release_ref": pv.release_ref, "prompt_hash": pv.prompt_hash,
              "approved_releases": sorted(approved)}
    if pv.release_ref not in approved:
        return ctx.fb.breach(
            rule, f"{run.run_id} executed on release {pv.release_ref}, which is not among the "
                  f"agent's approved prompt releases.",
            run_ref=run.run_id, values={**values, "approved": False}, refs=refs)
    expected = approved[pv.release_ref].get("prompt_hash")
    if expected not in (None, pv.prompt_hash):
        return ctx.fb.breach(
            rule, f"{run.run_id} claims approved release {pv.release_ref} but its prompt hash "
                  f"does not match the approved artifact.",
            run_ref=run.run_id, refs=refs,
            values={**values, "approved": True, "hash_matches": False, "approved_hash": expected})
    return ctx.fb.satisfied(
        rule, f"{run.run_id} executed on approved release {pv.release_ref}"
              + (" with a matching prompt hash." if expected else "."),
        run_ref=run.run_id, refs=refs,
        values={**values, "approved": True, "hash_matches": expected is not None or None})


def _tec_06(rule: Rule, run: Run, ctx: ProvenanceContext) -> Fact:
    """Every tool server used was declared and is authorised.

    Two separate failures with one shape. A server the *regulator* never
    authorised for that tool is F33. A server the *operator's own AgentCard*
    never declared is a different problem — the agent is reaching somewhere its
    own published description does not admit to — and the statement
    distinguishes them, because the supervisory response differs.

    The tool NAME in an unauthorised call is almost always one the agent may
    legitimately call. That is precisely why the server is what gets pinned.
    """
    unauthorised, undeclared, refs = [], [], []
    for tc in run.construction_context.tool_calls:
        refs.append(EvidenceRef(kind="tool_call", ref=f"tool_calls[{tc.sequence}]",
                                value=f"{tc.tool_name} -> {tc.server_id}"))
        spec = ctx.tools.get(tc.tool_name)
        if spec and tc.server_id not in spec["authorised_server_ids"]:
            unauthorised.append(f"{tc.tool_name} -> {tc.server_id}")
        elif ctx.declared_servers is not None and tc.server_id not in ctx.declared_servers:
            undeclared.append(f"{tc.tool_name} -> {tc.server_id}")
    values = {"tool_calls": len(run.construction_context.tool_calls),
              "unauthorised": unauthorised, "undeclared": undeclared,
              "agent_card_filed": ctx.declared_servers is not None}
    if unauthorised or undeclared:
        parts = []
        if unauthorised:
            parts.append(f"{len(unauthorised)} call(s) to a server not authorised for that tool "
                         f"({'; '.join(unauthorised)})")
        if undeclared:
            parts.append(f"{len(undeclared)} call(s) to a server the agent's own card does not "
                         f"declare ({'; '.join(undeclared)})")
        return ctx.fb.breach(rule, f"{run.run_id}: " + "; ".join(parts) + ".",
                             run_ref=run.run_id, values=values, refs=refs)
    if ctx.declared_servers is None:
        return ctx.fb.absent(
            rule, "missing_block",
            f"{run.run_id}: every tool server called is authorised for its tool, but no agent "
            f"card was filed, so whether the agent declared them cannot be checked.",
            missing="agent_card.declared_tool_servers", run_ref=run.run_id, values=values)
    return ctx.fb.satisfied(
        rule, f"{run.run_id}: all {len(refs)} tool call(s) went to servers that are both "
              f"authorised for the tool and declared on the agent card.",
        run_ref=run.run_id, values=values, refs=refs)


def _crd_01(rule: Rule, ctx: ProvenanceContext) -> Fact:
    """F34 — the card claims what the credential never granted, or is unsigned."""
    card = ctx.card
    if card is None:
        return ctx.fb.absent(rule, "missing_block", "No agent card was filed, so the operator's own "
                             "description of the agent cannot be compared to its credential.",
                             missing="agent_card")
    granted = set(ctx.credential_capabilities)
    excess = sorted(set(card.declared_capabilities) - granted)
    unsigned = not card.signature
    problems = []
    if excess:
        problems.append(f"the card declares {', '.join(excess)}, which the credential does not grant")
    if unsigned:
        problems.append("the card carries no signature")
    return ctx.fb.verdict(
        rule, bool(problems),
        "The agent card and the credential disagree: " + "; ".join(problems) + ".",
        f"The agent card's {len(card.declared_capabilities)} declared capability(ies) are within the "
        f"credential's grant, and the card is signed.",
        values={"declared_capabilities": card.declared_capabilities, "credential_capabilities": sorted(granted),
                "excess": excess, "signed": not unsigned},
        refs=[EvidenceRef(kind="field", ref="agent_card.declared_capabilities", value=card.declared_capabilities)])


def _rec_01(rule: Rule, ctx: ProvenanceContext) -> Fact:
    """PRV-REC-01's evidence: the four sources side by side."""
    card = ctx.card
    observed_servers = sorted({tc.server_id for r in ctx.runs for tc in r.construction_context.tool_calls})
    observed_models = sorted({r.construction_context.model.observed_version for r in ctx.runs})
    declared_models = sorted({r.construction_context.model.declared_version for r in ctx.runs})
    observed_releases = sorted({r.construction_context.policy_version.release_ref for r in ctx.runs})
    agent = ctx.agent or {}
    return ctx.fb.measurement(
        "four_sources",
        f"Card, credential, register and {len(ctx.runs)} run(s) of observed calls laid side by side.",
        rule=rule,
        values={
            "agent_card": {"filed": card is not None,
                           "declared_capabilities": card.declared_capabilities if card else None,
                           "declared_tool_servers": card.declared_tool_servers if card else None,
                           "signed": bool(card and card.signature)},
            "credential": {"capabilities": ctx.credential_capabilities},
            "register": {"present": ctx.agent is not None, "classification": agent.get("classification"),
                         "approved_prompt_releases": [r.get("release_ref") for r in agent.get("approved_prompt_releases", [])],
                         "validated_models": [v.get("model_version") for v in agent.get("validation_evidence", [])]},
            "observed": {"tool_servers": observed_servers, "models": observed_models,
                         "declared_models": declared_models, "prompt_releases": observed_releases},
            "deployment_target": ctx.deployment_target,
        })


_RUN_CHECKERS = {
    "observed_model_matches_declared": _tec_02,
    "prompt_bound_to_released_artifact": _tec_05,
    "tool_servers_declared": _tec_06,
}

_DOSSIER_CHECKERS = {
    "agent_card_matches_credential": _crd_01,
    "four_sources_reconcile": _rec_01,
}

_PROVENANCE_CHECKERS = {**_RUN_CHECKERS, **_DOSSIER_CHECKERS}

# The three rules that read construction_context and once lived in the KYA
# book. KYA's dispatcher skips these types if it ever meets them again — the
# split is on evidence rather than topic, see kya-ruleset.md Part 3.5.
PROVENANCE_RULE_TYPES = frozenset(_RUN_CHECKERS)


def run_provenance_checks(dossier: LoadedDossier, ruleset: Ruleset, *,
                          ctx: ProvenanceContext | None = None) -> list[Fact]:
    """Every rule in the Provenance book, over the dossier."""
    ctx = ctx or build_context(dossier)
    return evaluate_ruleset(ruleset, builder=ctx.fb, ctx=ctx, runs=dossier.runs,
                            dossier_checkers=_DOSSIER_CHECKERS, run_checkers=_RUN_CHECKERS,
                            module="agents/provenance_checks.py")
