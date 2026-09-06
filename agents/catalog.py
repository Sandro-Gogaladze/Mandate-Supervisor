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
from registry import loader

PEERS = ("mandate", "kya", "provenance", "injection", "counterparty", "consent", "log", "drift")
AGENTS = dict(zip((*PEERS, "control_assurance", "systemic"),
                 (MandateAgent, KYAAgent, ProvenanceAgent, InjectionAgent, CounterpartyAgent,
                  ConsentAgent, LogAgent, DriftAgent, ControlAssuranceAgent, SystemicAgent)))
RULESET_LOADERS = {name: getattr(loader, f"load_{'ctl' if name == 'control_assurance' else name}_ruleset")
                   for name in (*PEERS, "control_assurance")}
# Systemic has a book like every other specialist: its four sweeps carry dials,
# and a dial living in a Python default is the one thing the sandbox cannot
# tune, sweep or promote — which is precisely backwards for the market-level
# layer a regulator is uniquely placed to supervise.
RULESET_LOADERS["systemic"] = loader.load_systemic_ruleset
