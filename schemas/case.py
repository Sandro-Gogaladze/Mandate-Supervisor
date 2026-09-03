"""Case bundle — one full submission.

Field shapes follow docs/phases/01-synthetic-data.md §2.7.

`label`, `planted_defects` and `narrative` are eval-only ground truth. A real
submission never carries them; data/loader.py strips them before a case
reaches the pipeline.

`label` was a closed seven-value Literal drawn from the original corpus. The
coverage model names 73 distinct failures, so a fixed enum would have to be
edited every time a case explores a new one — the same rules-as-data argument
that loosened RuleType. It is now a validated slug, and `planted_defects`
carries the ground truth that actually matters: which failures this case is
built to make detectable, by their F-numbers in docs/coverage-model.md. An
empty list means a clean case, and asserts the run should find nothing.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .kya import KYACredential
from .mandate import MandateChain
from .submission import ConsentCeremony, ConstructionContext, Controls
from .transaction import TransactionLogEntry

ScenarioLabel = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=3, max_length=48),
]

# "F29", "F72" — the failure ids in docs/coverage-model.md.
FailureId = Annotated[str, StringConstraints(pattern=r"^F\d{1,2}$")]


class Firm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firm_id: str
    name: str
    sector: str
    hq: str


class CaseBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    label: ScenarioLabel | None = None
    planted_defects: list[FailureId] = Field(default_factory=list)
    narrative: str | None = None
    firm: Firm
    kya_credential: KYACredential
    mandate_chain: MandateChain
    transaction_history: list[TransactionLogEntry]

    # The three blocks beyond the signed artifacts (schemas/submission.py).
    # Optional by design: a firm that omits one does not get a clean case —
    # every rule needing it returns an `absent` fact and the run emits a
    # data-gap finding. Absence is evidence, not a silent skip.
    consent_ceremony: ConsentCeremony | None = None
    construction_context: ConstructionContext | None = None
    controls: Controls | None = None
