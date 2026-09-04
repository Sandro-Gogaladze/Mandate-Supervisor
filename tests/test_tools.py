"""The tool layer and its permission map."""
from __future__ import annotations

import json

import pytest

from agents.tools import (
    AGENT_TOOLS,
    ToolNotPermittedError,
    UnknownAgentError,
    execute_tool,
    tools_for,
)
from tests.corpus import HAL, seed


def test_only_the_investigator_has_tools_and_every_agent_is_registered() -> None:
    assert AGENT_TOOLS["investigator"]
    for agent in ("mandate", "kya", "log", "drift", "drafting", "orchestrator", "synthesizer"):
        assert AGENT_TOOLS[agent] == frozenset()
        assert tools_for(agent) == []


def test_unregistered_agent_raises_never_defaults(kst) -> None:
    with pytest.raises(UnknownAgentError):
        tools_for("portfolio_sweeper")
    with pytest.raises(UnknownAgentError):
        execute_tool("portfolio_sweeper", "get_transactions", {}, dossier=kst)


def test_execution_rechecks_the_map(kst) -> None:
    with pytest.raises(ToolNotPermittedError):
        execute_tool("log", "get_transactions", {}, dossier=kst)


def test_get_transactions_filters_and_delimits_firm_text(kst) -> None:
    result = execute_tool("investigator", "get_transactions", {"counterparty_id": "MER-QVC-8801"}, dossier=kst)
    assert result["count"] == 4
    row = result["transactions"][0]
    assert row["counterparty_name"].startswith("<<<UNTRUSTED_FIRM_TEXT>>>")
    by_run = execute_tool("investigator", "get_transactions", {"run_id": "RUN-2026-0811-0043"}, dossier=kst)
    assert by_run["count"] == 1 and by_run["transactions"][0]["amount"] == 708.0


def test_no_tool_result_ever_contains_firm_authored_free_text(kst) -> None:
    """The three injection channels — line-item text, the shopper's prompt,
    retrieved content — stay out of the investigator's reach entirely."""
    untrusted = set()
    for r in kst.runs:
        untrusted.add(r.user_prompt)
        for li in (r.cart.line_items if r.cart else []):
            untrusted.add(li.description)
        for tc in r.construction_context.tool_calls:
            if tc.result_excerpt:
                untrusted.add(tc.result_excerpt.text)
    args = {
        "get_transactions": {},
        "get_counterparty_profile": {"counterparty_id": "MER-QVC-8801"},
        "get_issuer_record": {"issuer_id": "ISS-002"},
        "get_rule": {"rule_id": "MND-SEM-01"},
        "recompute_stats": {"kind": "log"},
        "get_case_findings": {},
        "get_run": {"run_id": "RUN-2026-0715-0025"},
    }
    for tool in sorted(AGENT_TOOLS["investigator"]):
        blob = json.dumps(execute_tool("investigator", tool, args[tool], dossier=kst), ensure_ascii=False)
        for text in untrusted:
            assert text not in blob, (tool, text[:40])


def test_counterparty_profile_reaches_across_the_ledger(kst, store) -> None:
    seed(store); seed(store, HAL)
    profile = execute_tool("investigator", "get_counterparty_profile",
                           {"counterparty_id": "MER-QVC-8801"}, dossier=kst, store=store)
    assert profile["this_case"]["transaction_count"] == 4
    assert profile["registry"]["beneficial_owner"] is None
    assert "beneficial_owner_unresolved" in profile["registry"]["watchlist_flags"]
    assert [c["case_id"] for c in profile["other_cases"]] == ["DOSSIER-HAL-2026-001"]


def test_recompute_stats_with_a_different_window(kst) -> None:
    default = execute_tool("investigator", "recompute_stats", {"kind": "log"}, dossier=kst)
    tight = execute_tool("investigator", "recompute_stats", {"kind": "log", "window_hours": 0.01}, dossier=kst)
    assert max(len(c["transaction_ids"]) for c in default["structuring_clusters"]) >= \
        max(len(c["transaction_ids"]) for c in tight["structuring_clusters"])
    drift = execute_tool("investigator", "recompute_stats", {"kind": "drift", "baseline_window_days": 14}, dossier=kst)
    assert drift["baseline_count"] + drift["comparison_count"] == 102


def test_get_rule_and_issuer_answer_unknowns_gracefully(kst) -> None:
    rule = execute_tool("investigator", "get_rule", {"rule_id": "LOG-STR-01"}, dossier=kst)
    assert rule["type"] == "transaction_structuring_detected"
    ctl = execute_tool("investigator", "get_rule", {"rule_id": "CTL-EFF-01"}, dossier=kst)
    assert ctl["ruleset"] == "CTL-RULESET"
    assert execute_tool("investigator", "get_rule", {"rule_id": "XXX-999"}, dossier=kst)["found"] is False
    absent = execute_tool("investigator", "get_issuer_record", {"issuer_id": "ISS-099"}, dossier=kst)
    assert absent["present_in_trust_registry"] is False


def test_get_run_returns_the_chain_in_structure_only(kst) -> None:
    run = execute_tool("investigator", "get_run", {"run_id": "RUN-2026-0811-0043"}, dossier=kst)
    assert run["cart"]["cart_total"] == 708.0 and run["intent"]["max_transaction_amount"] == 500.0
    assert run["controls_evaluated"][0] == {"control_id": "KST-CTL-001", "outcome": "triggered",
                                           "override_by": "ops-analyst-11"}
    assert "description" not in json.dumps(run["cart"]["line_items"])
    assert execute_tool("investigator", "get_run", {"run_id": "RUN-NOPE"}, dossier=kst)["found"] is False
