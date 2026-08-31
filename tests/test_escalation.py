from pipeline.escalation import escalation_targets, observations_for, target_agent_for
from schemas import Observation


def _obs(agent: str, note: str) -> Observation:
    return Observation(case_id="CASE-TEST", agent=agent, note=note, cited_evidence="x")


def test_default_target_is_the_observations_own_agent() -> None:
    obs = _obs("kya", "Issuer name resembles a trusted one.")
    assert target_agent_for(obs) == "kya"


def test_cross_agent_reference_routes_to_the_named_agent() -> None:
    obs = _obs("drift", "This new counterparty warrants a specific KYA/counterparty verification check.")
    assert target_agent_for(obs) == "kya"


def test_word_boundary_prevents_false_match_inside_another_word() -> None:
    # "log" must not match inside "dialogue", "catalogue", "backlog" etc.
    obs = _obs("drift", "Worth noting in the dialogue with the operator, per the catalogue of vendors.")
    assert target_agent_for(obs) == "drift"  # no real cross-reference, stays with drift


def test_mentioning_own_agent_by_name_does_not_redirect() -> None:
    obs = _obs("log", "The log shows a burst of transactions.")
    assert target_agent_for(obs) == "log"


def test_escalation_targets_deduplicates_and_sorts() -> None:
    observations = [
        _obs("drift", "Worth a KYA look at this counterparty."),
        _obs("kya", "Issuer name is unusual."),
        _obs("log", "Round-number clustering."),
    ]
    assert escalation_targets(observations) == ["kya", "log"]


def test_observations_for_filters_by_resolved_target_not_origin() -> None:
    observations = [
        _obs("drift", "Worth a KYA look at this counterparty."),
        _obs("kya", "Issuer name is unusual."),
    ]
    kya_bound = observations_for("kya", observations)
    assert len(kya_bound) == 2  # both route to kya
    assert observations_for("drift", observations) == []


def test_mandate_is_never_an_escalation_target() -> None:
    # Mandate's semantic subcheck never produces Observations at all, but
    # even a hypothetical note naming it shouldn't be treated as escalatable.
    observations = [_obs("log", "Might be worth a Mandate re-check.")]
    assert escalation_targets(observations) == []
