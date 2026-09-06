"""The policy sandbox: drafts fork, sweeps measure, promotion is gated."""
import asyncio
import json
import shutil

import pytest

from registry.loader import RULESETS_DIR
from sandbox import drafts as drafts_module
from sandbox import service as service_module
from sandbox.drafts import (
    DraftError,
    active_ruleset,
    create_draft,
    delete_draft,
    edit_rule,
    list_drafts,
    ruleset_digest,
)
from sandbox.service import promote, start_sweep, version_graph
from sandbox.store import SweepStore, compare
from sandbox.sweep import corpus_digest, pins, run_sweep


@pytest.fixture(autouse=True)
def sandbox_writes_to_tmp(tmp_path, monkeypatch):
    """Every path the sandbox writes to, redirected out of the repo.

    The sandbox is the one component whose job is to write into `registry/` —
    drafts beside the rulebook, and on promotion the rulebook itself. Pointed
    at the real directory a test run edits the policy it is testing against:
    a draft left behind by a run that died before teardown broke every
    subsequent run, and a promotion test that ever reached its happy path
    would republish the book in force. Both are the same missing seam.

    `active_ruleset()` still reads the real registry, which is what we want —
    the fixture isolates the WRITES, not the thing under test.
    """
    rulesets = tmp_path / "rulesets"
    shutil.copytree(RULESETS_DIR, rulesets, ignore=shutil.ignore_patterns("published"))
    monkeypatch.setattr(drafts_module, "DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(service_module, "RULESETS_DIR", rulesets)
    monkeypatch.setattr(service_module, "PUBLISHED_DIR", rulesets / "published")
    return rulesets


@pytest.fixture
def sweeps(tmp_path):
    return SweepStore(tmp_path / "sandbox.db")


@pytest.fixture
def draft():
    d = create_draft(domain="kya", label="test fixture", created_by="ana")
    yield d
    try:
        delete_draft(d.draft_id)
    except DraftError:
        pass


# --- drafts ----------------------------------------------------------------

def test_a_draft_is_a_fork_not_an_edit_in_place(draft) -> None:
    """A published version must stay exactly as it was when a sweep measured
    it, or a scorecard expires silently the moment someone tunes a knob."""
    before = ruleset_digest(active_ruleset("kya"))
    edit_rule(draft.draft_id, "KYA-ISS-04", params={"max_reaccreditation_age_days": 365})
    assert ruleset_digest(active_ruleset("kya")) == before


def test_editing_changes_the_digest_and_records_what_changed(draft) -> None:
    edited = edit_rule(draft.draft_id, "KYA-ISS-04",
                       params={"max_reaccreditation_age_days": 365})
    assert edited.digest != draft.digest
    assert edited.edits == ["KYA-ISS-04 max_reaccreditation_age_days 730 → 365"]


def test_a_parameter_the_rule_does_not_take_is_refused(draft) -> None:
    """typed_params() validates on write, so a bad edit fails here rather
    than at sweep time when it would look like a policy result."""
    with pytest.raises(Exception):
        edit_rule(draft.draft_id, "KYA-ISS-04", params={"not_a_real_knob": 1})


def test_drafts_are_invisible_to_the_registry_loader(draft) -> None:
    """The isolation is structural: there is no loader function that reads
    registry/drafts/, so a live review cannot pick one up by mistake."""
    import registry.loader as loader
    assert not any("draft" in name.lower() for name in dir(loader))
    assert loader.load_kya_ruleset().version == active_ruleset("kya").version


# --- sweeps ----------------------------------------------------------------

def test_a_mechanical_sweep_scores_the_corpus_without_labels_reaching_the_pipeline() -> None:
    result = asyncio.run(run_sweep())
    assert result.overall.tp > 0 and result.clean_runs > 0
    # Both dossiers carry planted defects, so neither may be authorised.
    assert result.dossiers and all(d.planted_defects > 0 for d in result.dossiers)
    assert all(d.correct for d in result.dossiers)


def test_a_sweep_names_the_domains_it_could_not_evaluate() -> None:
    """Transaction Patterns is 0/3 computable, so a mechanical total that
    ignored it would imply coverage it lacks.

    Behavioural Drift is no longer on that list: DRIFT-BAS-01 asks whether the
    baseline can carry a drift question at all, which is arithmetic, so a
    mechanical sweep now has something real to say about the domain even
    though both of its verdicts remain judged.
    """
    result = asyncio.run(run_sweep())
    assert set(result.unevaluated_domains) == {"log"}


def test_dead_rules_are_reported() -> None:
    """The cheapest useful signal: a rule that never fires on any labelled
    case. Needs no labels at all, just a run."""
    result = asyncio.run(run_sweep())
    assert result.dead_rules
    assert all(result.per_rule[r].fired == 0 for r in result.dead_rules)


def test_rule_scores_carry_counts_so_a_rate_over_n_of_one_cannot_pose_as_evidence() -> None:
    result = asyncio.run(run_sweep())
    thin = [s for s in result.per_rule.values() if 0 < s.labelled < 5]
    assert thin, "the corpus is small enough that some rule must be thin"
    assert all(not s.trustworthy for s in thin)


# --- comparison ------------------------------------------------------------

def test_tightening_a_threshold_shows_its_cost(sweeps, draft) -> None:
    base = asyncio.run(start_sweep(ruleset_ref="kya", store=sweeps))
    edit_rule(draft.draft_id, "KYA-ISS-04", params={"max_reaccreditation_age_days": 200})
    candidate = asyncio.run(start_sweep(ruleset_ref=draft.draft_id, store=sweeps))

    result = compare(base, candidate)
    assert result.comparable
    # Nothing new caught, and it costs false positives — exactly the finding
    # the sandbox exists to produce.
    assert candidate.result.overall.tp == base.result.overall.tp
    assert candidate.result.overall.fp > base.result.overall.fp
    assert any(f.direction == "new_false_positive" for f in result.flips)


def test_sweeps_on_different_pins_refuse_to_be_compared(sweeps, draft) -> None:
    base = asyncio.run(start_sweep(ruleset_ref="kya", store=sweeps))
    other = base.model_copy(update={
        "sweep_id": "swp-other",
        "pins": base.pins.model_copy(update={"corpus_digest": "sha256:different"}),
    })
    result = compare(base, other)
    assert not result.comparable
    assert "corpus" in result.incomparable_reason


# --- promotion -------------------------------------------------------------

def test_promotion_requires_a_sweep_of_this_exact_draft(sweeps, draft, store) -> None:
    base = asyncio.run(start_sweep(ruleset_ref="kya", store=sweeps))
    with pytest.raises(ValueError, match="did not measure this draft"):
        promote(draft_id=draft.draft_id, sweep_id=base.sweep_id, promoted_by="ana",
                rationale="because", store=sweeps, ledger=store)


def test_promotion_refuses_a_sweep_taken_before_the_last_edit(sweeps, draft, store) -> None:
    """Promoting on a scorecard that measured a different rulebook would be
    worse than promoting with no evidence, because it would look like evidence."""
    swept = asyncio.run(start_sweep(ruleset_ref=draft.draft_id, store=sweeps))
    edit_rule(draft.draft_id, "KYA-LIF-03", severity_weight=0.9)
    with pytest.raises(ValueError, match="did not measure this draft"):
        promote(draft_id=draft.draft_id, sweep_id=swept.sweep_id, promoted_by="ana",
                rationale="because", store=sweeps, ledger=store)


def test_a_promotion_republishes_the_book_and_keeps_the_outgoing_one(
        sweeps, draft, store, sandbox_writes_to_tmp) -> None:
    """The happy path, which had no test at all — every other promotion case
    asserts a refusal, so nothing proved the act it is gating actually works.

    It is only safe to write because `sandbox_writes_to_tmp` gives promotion
    somewhere to publish that is not the repo.
    """
    base = active_ruleset("kya")
    edit_rule(draft.draft_id, "KYA-ISS-04", params={"max_reaccreditation_age_days": 365})
    swept = asyncio.run(start_sweep(ruleset_ref=draft.draft_id, store=sweeps))

    result = promote(draft_id=draft.draft_id, sweep_id=swept.sweep_id, promoted_by="ana",
                     rationale="tighter re-accreditation age, no new false positives",
                     store=sweeps, ledger=store)
    assert result["from_version"] == base.version and result["to_version"] != base.version

    published = json.loads((sandbox_writes_to_tmp / "kya.json").read_text())
    assert published["version"] == result["to_version"]
    rule = next(r for r in published["rules"] if r["rule_id"] == "KYA-ISS-04")
    assert rule["params"]["max_reaccreditation_age_days"] == 365
    # The outgoing book stays readable, so the version graph is a fact on disk.
    assert (sandbox_writes_to_tmp / "published" / f"kya@{base.version}.json").exists()

    event = next(e for e in store.events_for("registry:kya"))
    assert event.event_type == "ruleset_promoted"
    assert event.payload["sweep_id"] == swept.sweep_id
    assert event.actor == "human:ana"


def test_promotion_needs_a_rationale(sweeps, draft, store) -> None:
    swept = asyncio.run(start_sweep(ruleset_ref=draft.draft_id, store=sweeps))
    with pytest.raises(ValueError, match="rationale"):
        promote(draft_id=draft.draft_id, sweep_id=swept.sweep_id, promoted_by="ana",
                rationale="   ", store=sweeps, ledger=store)


def test_the_version_graph_shows_drafts_and_whether_they_have_been_swept(sweeps, draft) -> None:
    graph = version_graph("kya", store=sweeps)
    assert graph["active"]["version"] == active_ruleset("kya").version
    entry = next(d for d in graph["drafts"] if d["draft"]["draft_id"] == draft.draft_id)
    assert entry["swept"] is False

    asyncio.run(start_sweep(ruleset_ref=draft.draft_id, store=sweeps))
    entry = next(d for d in version_graph("kya", store=sweeps)["drafts"]
                 if d["draft"]["draft_id"] == draft.draft_id)
    assert entry["swept"] is True


def test_pins_are_stable_across_calls() -> None:
    assert corpus_digest() == corpus_digest()
    assert pins().mode == "mechanical" and pins(mode="live").mode == "live"


def test_a_draft_of_every_domain_actually_reaches_the_graph() -> None:
    """The graph resolves a rulebook per dispatched AGENT. registry.loader
    calls Control Assurance's book "controls" while the agent is
    "control_assurance" — keying overrides the registry's way meant a draft
    of that domain was accepted and then silently ignored."""
    from agents.catalog import RULESET_LOADERS as AGENT_LOADERS
    from sandbox.drafts import RULESET_LOADERS as SANDBOX_LOADERS
    editable = {name for name, load in SANDBOX_LOADERS.items() if load() is not None}
    assert "control_assurance" in editable
    assert editable <= set(AGENT_LOADERS), "every editable domain must be a dispatchable agent"


def test_judged_only_failures_are_derived_from_the_rulebook_not_hardcoded() -> None:
    """`rule.evaluation` is the source of truth. The hardcoded list inherited
    from eval/__main__.py was wrong in both directions: F32 (INJ-ACT-01,
    judged) was missing so its labels counted as missed, and F55
    (CPT-NEW-01, computable) was excluded so labels a code rule catches were
    dropped from the score."""
    from agents.catalog import RULESET_LOADERS
    from sandbox.sweep import judged_only_failures
    books = {name: load() for name, load in RULESET_LOADERS.items()}
    judged = judged_only_failures(books)
    assert "F32" in judged, "INJ-ACT-01 is judged; a mechanical sweep cannot establish F32"
    assert "F49" in judged
    assert "F55" not in judged, "CPT-NEW-01 is computable"


def test_a_mechanical_sweep_reports_what_it_could_not_score() -> None:
    """The denominator must not quietly shrink to flatter itself: labels only
    a judged rule could establish are listed, not dropped.

    Ferrymead is the case that makes this load-bearing. Its defects are ALL
    judged — a mechanical sweep of it scores almost nothing, and a sweep that
    dropped what it could not reach would report that submission as clean."""
    result = asyncio.run(run_sweep())
    assert result.not_scoreable
    assert {l.failure for l in result.not_scoreable} == {"F32", "F35", "F38", "F49"}
    # …and none of them is also counted as a miss.
    missed = {(m.dossier_id, m.run_ref, m.failure) for m in result.missed}
    excluded = {(l.dossier_id, l.run_ref, l.failure) for l in result.not_scoreable}
    assert not (missed & excluded)
