"""One registry for graph construction, policy coverage and evaluation."""
from agents.mandate import MandateAgent
from agents.kya import KYAAgent
from agents.log import LogAgent
from agents.drift import DriftAgent
from agents.provenance import ProvenanceAgent
from agents.injection import InjectionAgent
from agents.counterparty import CounterpartyAgent
from agents.consent import ConsentAgent
from agents.control_assurance import ControlAssuranceAgent
from agents.systemic import SystemicAgent
from agents.red_team import RedTeamAgent
from registry import loader

PEERS = ("mandate", "kya", "provenance", "injection", "counterparty", "consent", "log", "drift")
AGENTS = dict(zip((*PEERS, "control_assurance", "systemic", "red_team"),
                 (MandateAgent, KYAAgent, ProvenanceAgent, InjectionAgent, CounterpartyAgent,
                  ConsentAgent, LogAgent, DriftAgent, ControlAssuranceAgent, SystemicAgent, RedTeamAgent)))
RULESET_LOADERS = {name: getattr(loader, f"load_{'ctl' if name == 'control_assurance' else name}_ruleset")
                   for name in (*PEERS, "control_assurance")}
RULESET_LOADERS.update(systemic=lambda: None, red_team=lambda: None)
