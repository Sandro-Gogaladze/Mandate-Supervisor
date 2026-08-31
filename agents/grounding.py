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
"""
from __future__ import annotations

from schemas import DraftReport, Finding, Observation

__all__ = ["check_grounding"]


def check_grounding(
    report: DraftReport,
    findings: list[Finding],
    observations: list[Observation],
) -> list[str]:
    problems: list[str] = []
    real_ids = {f.finding_id for f in findings}

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

    return problems
