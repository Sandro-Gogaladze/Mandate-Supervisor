"""Stage 9 — the tool layer and its permission map (architecture-v2 §16)."""
from __future__ import annotations

import pytest

from agents.tools import (
    AGENT_TOOLS,
    ToolNotPermittedError,
    UnknownAgentError,
    execute_tool,
    tools_for,
)
from data.loader import CASES_DIR, load_raw_case_json
from ingestion.normalize import build_verification_context, normalize_case
from ledger import LedgerStore
from ledger.seed import submit_case

_CTX = build_verification_context()


def _case(name: str = "case-006-drift.json"):
    return normalize_case(CASES_DIR / name, _CTX)


def test_only_the_investigator_has_tools_and_every_agent_is_registered() -> None:
    assert AGENT_TOOLS["investigator"]
    for agent in ("mandate", "kya", "log", "drift", "drafting", "orchestrator", "synthesizer"):
        assert AGENT_TOOLS[agent] == frozenset()
        assert tools_for(agent) == []


def test_unregistered_agent_raises_never_defaults() -> None:
    with pytest.raises(UnknownAgentError):
        tools_for("portfolio_sweeper")
    with pytest.raises(UnknownAgentError):
        execute_tool("portfolio_sweeper", "get_transactions", {}, case=_case())


def test_execution_rechecks_the_map() -> None:
    # even a specialist that somehow bound a tool cannot execute it
    with pytest.raises(ToolNotPermittedError):
        execute_tool("log", "get_transactions", {}, case=_case())


def test_get_transactions_filters_and_delimits_firm_text() -> None:
    result = execute_tool("investigator", "get_transactions",
                          {"counterparty_id": "MER-BEF-005"}, case=_case())
    assert result["count"] == 17
    row = result["transactions"][0]
    assert row["counterparty_name"].startswith("<<<UNTRUSTED_FIRM_TEXT>>>")
    assert "description" not in row  # transaction rows never carry line-item text


def test_no_tool_result_ever_contains_line_item_descriptions() -> None:
    """The one adversarial field in the schema stays out of the investigator's
    reach entirely — checked against the injection case itself."""
    import json

    case = _case("case-007-prompt-injection.json")
    injected = "gift-card top-up of ₾1,200 to account GC-7734-INTL"
    for tool in sorted(AGENT_TOOLS["investigator"]):
        args = {
            "get_transactions": {},
            "get_counterparty_profile": {"counterparty_id": "MER-KGS-001"},
            "get_issuer_record": {"issuer_id": "ISS-001"},
            "get_rule": {"rule_id": "MND-SEM-01"},
            "recompute_stats": {"kind": "log"},
            "get_case_findings": {},
        }[tool]
        result = execute_tool("investigator", tool, args, case=case)
        assert injected not in json.dumps(result, ensure_ascii=False), tool


def test_counterparty_profile_reaches_across_the_ledger(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.db")
    submit_case(store, load_raw_case_json(CASES_DIR / "case-006-drift.json"))
    # a second case sharing the counterparty — fabricate by reusing 006 under a new id
    other = load_raw_case_json(CASES_DIR / "case-006-drift.json")
    other["case_id"] = "CASE-2026-099"
    submit_case(store, other)

    profile = execute_tool("investigator", "get_counterparty_profile",
                           {"counterparty_id": "MER-BEF-005"}, case=_case(), store=store)
    assert profile["this_case"]["transaction_count"] == 17
    assert profile["this_case"]["first_seen"].startswith("2026-07-11")
    assert [c["case_id"] for c in profile["other_cases"]] == ["CASE-2026-099"]


def test_recompute_stats_with_a_different_window() -> None:
    case = _case("case-005-structuring.json")
    default = execute_tool("investigator", "recompute_stats", {"kind": "log"}, case=case)
    tight = execute_tool("investigator", "recompute_stats",
                         {"kind": "log", "window_hours": 0.1}, case=case)
    # the 17/22-minute cluster survives a 24h window but splits at 6 minutes
    default_max = max(len(c["transaction_ids"]) for c in default["structuring_clusters"])
    tight_max = max(len(c["transaction_ids"]) for c in tight["structuring_clusters"])
    assert default_max >= 3
    assert tight_max < default_max


def test_get_rule_and_issuer_answer_unknowns_gracefully() -> None:
    case = _case()
    rule = execute_tool("investigator", "get_rule", {"rule_id": "LOG-STR-01"}, case=case)
    assert rule["type"] == "transaction_structuring_detected"
    missing = execute_tool("investigator", "get_rule", {"rule_id": "XXX-999"}, case=case)
    assert missing["found"] is False
    absent = execute_tool("investigator", "get_issuer_record", {"issuer_id": "ISS-099"}, case=case)
    assert absent["present_in_trust_registry"] is False
