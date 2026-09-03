
# ---------------------------------------------------------------------------
# Parked while the pipeline migrates to the Dossier shape.
#
# These modules cover real behaviour that still matters, but every one of them
# built its fixture from data/cases/*.json — a corpus that no longer exists.
# They fail at IMPORT, not at assertion, so a skip mark cannot reach them and
# collection has to exclude them instead.
#
# Listed by name rather than matched by glob, deliberately: a glob would
# silently swallow any new test that happened to match, and the whole point of
# parking rather than deleting is that the missing coverage stays visible and
# counted. Each name comes off this list when a dossier fixture replaces its
# case one — migration-plan.md Phase 2/3.
# ---------------------------------------------------------------------------
collect_ignore = [
    "test_agents.py",
    "test_context_composition.py",
    "test_dispatch.py",
    "test_drafting_run.py",
    "test_drift_agent.py",
    "test_drift_reasoning.py",
    "test_end_to_end.py",
    "test_finding_id_collision.py",
    "test_ingestion.py",
    "test_investigator.py",
    "test_kya_agent.py",
    "test_log_agent.py",
    "test_log_reasoning.py",
    "test_mandate_agent.py",
    "test_mandate_reasoning.py",
    "test_orchestrator.py",
    "test_prompts.py",
    "test_skills.py",
    "test_step_stream.py",
    "test_tools.py",
    "test_triage_run.py",
    "test_uploads.py",
]
