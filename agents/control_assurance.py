"""Control Assurance (E1) — did the firm's own controls work?

The other rulebooks ask whether the AGENT misbehaved. This one asks whether
the firm's declared controls did their job — which is the question a
supervisor is actually empowered to act on, and the difference between a
supervision tool and a detection tool.

Two things make it different from every other specialist:

- **It runs AFTER the peer fan-out.** `CTL-EFF-01` asks whether a control
  that *should* have triggered did — which means knowing the risk
  materialised, and that is somebody else's finding. `peers_from_facts()`
  turns the peers' breach facts into run → failure ids through the rules'
  own `failures` declarations; given no peers, EFF-01 is `absent/awaiting_peers`.
- **Posture is computable.** absent / failed / bypassed / ineffective /
  effective fall out of the CTL facts: a control that rejected an action
  and saw the payment settle anyway *failed*; one overridden into settlement
  was *bypassed*, by a named person; one that recorded `passed` on a run
  where its risk breached is *ineffective*; a risk with no declared control
  is *absent*; a control that rejected and held is *effective*. Recorded as
  `ControlPosture`. No model call is needed for it, so none is made.
"""
from __future__ import annotations

from schemas import Assessment, ControlPosture, EvidencePack, Fact, Ruleset
from schemas.dossier import LoadedDossier

from .base import SpecialistReview, floor, narrated
from .control_checks import run_control_checks


def peers_from_facts(facts: list[Fact], rulebooks: dict[str, Ruleset]) -> dict[str, set[str]]:
    """run_id -> the failure ids the peers' breach facts establish, via the
    rules' `failures` declarations. A breach of a rule that declares no
    failure contributes nothing — the map is data, not a guess."""
    failures = {r.rule_id: set(r.failures) for rs in rulebooks.values() for r in rs.rules if r.failures}
    peers: dict[str, set[str]] = {}
    latest = {(f.rule_id, f.run_ref): f for f in facts if f.kind != "measurement"}
    for f in latest.values():
        if f.kind == "breach" and f.run_ref and f.rule_id in failures:
            peers.setdefault(f.run_ref, set()).update(failures[f.rule_id])
    return peers


def peers_from_evidence(
    facts: list[Fact], assessments: list[Assessment], rulebooks: dict[str, Ruleset]
) -> dict[str, set[str]]:
    """Merge deterministic breach facts with precise judged conclusions.

    Triage facts (for example an injection regex hit) are not the same thing
    as an instantiated catalogue failure. Judged assessments therefore feed
    Control Assurance directly, using their narrowed ``failure_ids`` where
    present and the rule mapping only for single-failure judged rules.
    """
    peers = peers_from_facts(facts, rulebooks)
    rules = {r.rule_id: r for book in rulebooks.values() for r in book.rules}
    for assessment in assessments:
        if assessment.verdict != "breach" or not assessment.rule_id:
            continue
        rule = rules.get(assessment.rule_id)
        if rule is None:
            continue
        if assessment.failure_ids is not None:
            failures = set(assessment.failure_ids) & set(rule.failures)
        else:
            failures = set(rule.failures) if len(rule.failures) == 1 else set()
        for run_ref in assessment.run_refs:
            if failures:
                peers.setdefault(run_ref, set()).update(failures)
    return peers


def classify_postures(facts: list[Fact], assessments: list[Assessment]) -> list[ControlPosture]:
    case_id = facts[0].case_id if facts else ""
    by_rule = {a.rule_id: a for a in assessments if a.rule_id}
    out: list[ControlPosture] = []

    def aid(rule_id: str) -> str | None:
        return by_rule[rule_id].assessment_id if rule_id in by_rule else None

    for f in facts:
        if f.rule_id == "CTL-REP-02" and f.kind == "breach":
            for risk in f.values.get("uncontrolled_risks", []):
                out.append(ControlPosture(case_id=case_id, assessment_id=aid(f.rule_id), posture="absent",
                                          narrative=f"No control is declared for {risk}, a risk the mandate creates."))
        elif f.rule_id == "CTL-DIS-04":
            for cid in f.values.get("rejected", []):
                if f.kind == "breach":
                    out.append(ControlPosture(case_id=case_id, assessment_id=aid(f.rule_id), control_id=cid,
                                              posture="failed",
                                              narrative=f"{cid} rejected the action on {f.run_ref} and the payment settled anyway."))
                elif f.kind == "satisfied" and not f.values.get("payment", True):
                    out.append(ControlPosture(case_id=case_id, control_id=cid, posture="effective",
                                              narrative=f"{cid} rejected the action on {f.run_ref} and no payment was authorised."))
        elif f.rule_id == "CTL-EFF-04" and f.kind == "breach":
            for cid in f.values.get("overridden", []):
                by = (f.values.get("overridden_by") or ["unknown"])[0]
                out.append(ControlPosture(case_id=case_id, assessment_id=aid(f.rule_id), control_id=cid,
                                          posture="bypassed", override_by=by,
                                          narrative=f"{cid} triggered on {f.run_ref} and was overridden by {by} into settlement."))
        elif f.rule_id == "CTL-EFF-01" and f.kind == "breach":
            for entry in f.values.get("silent_controls", []):
                cid = entry.split(" ")[0]
                out.append(ControlPosture(case_id=case_id, assessment_id=aid(f.rule_id), control_id=cid,
                                          posture="ineffective",
                                          narrative=f"{cid} recorded passed on {f.run_ref} where its own risk breached."))
    return out


class ControlAssuranceAgent:
    name = "control_assurance"

    def run(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
            evidence: EvidencePack | None = None,
            peers: dict[str, set[str]] | None = None) -> list[Fact]:
        return run_control_checks(dossier, ruleset, peers) if ruleset else []

    def assess(self, facts: list[Fact], ruleset: Ruleset | None, dossier: LoadedDossier, *,
               round: int = 1) -> list[Assessment]:
        return floor(facts, ruleset, dossier, agent=self.name, round=round) if ruleset else []

    async def review(self, dossier: LoadedDossier, ruleset: Ruleset | None, *,
                     evidence: EvidencePack | None = None, model=None,
                     peer_facts: list[Fact] | None = None,
                     peer_assessments: list[Assessment] | None = None,
                     rulebooks: dict[str, Ruleset] | None = None,
                     prior_observations=None, reviewer_directive: str | None = None,
                     prompts: dict | None = None, context: dict | None = None,
                     round: int = 1, narrate: bool = True) -> SpecialistReview:
        if ruleset is None:
            return SpecialistReview(facts=[], assessments=[])
        peers = peers_from_evidence(
            peer_facts, peer_assessments or [], rulebooks or {}
        ) if peer_facts is not None else None
        facts = self.run(dossier, ruleset, evidence=evidence, peers=peers)
        assessments = self.assess(facts, ruleset, dossier, round=round)
        # The one call this agent makes, and it decides nothing: five posture
        # values across fifteen rules is the least self-explanatory output in
        # the system, and the officer reads it first. Grounded in its own
        # assessments, so it cannot introduce a claim the rules did not make —
        # every verdict above stays computed, with no model in the chain.
        return await narrated(
            SpecialistReview(facts=facts, assessments=assessments,
                             postures=classify_postures(facts, assessments)),
            self.name, dossier, model=model, prompts=prompts, narrate=narrate)
