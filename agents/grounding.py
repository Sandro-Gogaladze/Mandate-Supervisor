"""Deterministic grounding validator for the drafting agent (PLAN item 12).

Pure Python, no LLM — the whole point is that "every claim cites a real
finding" gets verified mechanically against graph state, not judged by a
second model that could hallucinate right alongside the first. Returns a
list of human-readable problems; empty means grounded. The problems are
fed back verbatim into the drafting agent's retry prompt
(agents/drafting.py::RETRY_ADDENDUM), so each rule's message is written
to be actionable by the model, not just true.

The rules, mapped to CLAUDE.md's guardrail language:

- "every claim must cite a real finding" → every cited finding_id must
  exist (no invented citations), and, when findings exist at all, every
  section must carry at least one citation (no free-floating prose).
- Coverage: every finding must be cited by some section — a report that
  silently drops an inconvenient finding is as ungrounded as one that
  invents evidence.
- Observations stay quarantined: they may only appear in the labeled
  `open_observations_note` — required when observations exist (a report
  that hides open questions misleads the officer), forbidden when none do
  (a note summarizing nothing is fabrication).
- Characterisation: a section's declared `character` must match the
  verdicts of the findings it cites. Citations being real and complete
  said nothing about whether the section described them correctly — a
  satisfied check written up as a breach passed every rule above. Prose
  cannot be checked mechanically, so the drafter declares the claim as a
  typed field and this verifies the declaration against the data.
- The risk score: `overall_assessment` must state the computed total and
  tier. It is the one number in the report that rests on no finding —
  scoring is a pure function of ruleset weights — so it is also the one
  claim nothing else here can catch.
"""
from __future__ import annotations

import re

from schemas import DraftReport, Finding, Observation, RiskScore

__all__ = ["check_grounding"]


def _is_breach(finding: Finding) -> bool:
    """A finding carrying no severity weight is a rule that was SATISFIED —
    the same rule pipeline/scoring.py applies when it contributes 0.0."""
    return (finding.severity_weight or 0) > 0


def check_grounding(
    report: DraftReport,
    findings: list[Finding],
    observations: list[Observation],
    risk_score: RiskScore | None = None,
) -> list[str]:
    problems: list[str] = []
    real_ids = {f.finding_id for f in findings}
    by_id = {f.finding_id: f for f in findings}

    cited: set[str] = set()
    for i, section in enumerate(report.sections):
        for fid in section.cited_finding_ids:
            if fid not in real_ids:
                problems.append(
                    f"Section {i + 1} ({section.title!r}) cites finding_id {fid!r}, "
                    f"which does not exist in this case's findings."
                )
            cited.add(fid)
        if real_ids and not section.cited_finding_ids:
            problems.append(
                f"Section {i + 1} ({section.title!r}) cites no findings — every section "
                f"must rest on at least one cited_finding_id."
            )

        cited_real = [by_id[fid] for fid in section.cited_finding_ids if fid in by_id]
        if section.character is None:
            problems.append(
                f"Section {i + 1} ({section.title!r}) declares no character — set it to "
                f"'adverse', 'clear' or 'mixed' to match the verdicts of the findings it cites."
            )
        elif cited_real:
            breaches = sum(1 for f in cited_real if _is_breach(f))
            satisfied = len(cited_real) - breaches
            actual = "mixed" if breaches and satisfied else "adverse" if breaches else "clear"
            if section.character != actual:
                problems.append(
                    f"Section {i + 1} ({section.title!r}) is declared {section.character!r} but "
                    f"cites {breaches} finding(s) with severity and {satisfied} satisfied "
                    f"check(s) — it is {actual!r}. Either change the declaration or move the "
                    f"findings that do not belong in it to another section."
                )

    for fid in sorted(real_ids - cited):
        problems.append(
            f"Finding {fid!r} is not cited by any section — no finding may be silently omitted."
        )

    if not real_ids and report.sections:
        problems.append(
            "This case has zero findings but the report has sections — a clean review "
            "is stated in overall_assessment only, with no sections."
        )

    if observations and not report.open_observations_note:
        problems.append(
            f"{len(observations)} unverified observation(s) exist but open_observations_note "
            f"is empty — open items must be surfaced to the officer, labeled as unverified."
        )
    if not observations and report.open_observations_note:
        problems.append(
            "open_observations_note is set but this case has no observations — "
            "it must be null."
        )

    if risk_score is not None:
        stated = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", report.overall_assessment)]
        # Formatting is the model's ("18.875", "score of 18.875"); the VALUE is
        # not, so match numerically and reject a rounded restatement.
        if not any(abs(n - risk_score.total) < 1e-9 for n in stated):
            problems.append(
                f"overall_assessment does not state the risk score total {risk_score.total} — "
                f"state it exactly as given, not rounded or recomputed."
            )
        low = report.overall_assessment.lower()
        if risk_score.tier_label.lower() not in low and risk_score.tier.lower() not in low:
            problems.append(
                f"overall_assessment does not state the risk tier {risk_score.tier_label!r} — "
                f"state the tier exactly as given."
            )

    return problems
