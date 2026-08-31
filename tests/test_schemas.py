import json
from pathlib import Path

import pytest

from data.loader import load_labeled_case

CASES_DIR = Path(__file__).resolve().parent.parent / "data" / "cases"
CASE_FILES = sorted(CASES_DIR.glob("*.json"))


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: p.name)
def test_case_file_validates_against_schema(path: Path) -> None:
    # Goes through the loader (not raw CaseBundle.model_validate) since the
    # on-disk files carry QA-only `_*_note` annotations the loader strips —
    # see data/loader.py and docs/phases/01-synthetic-data.md §2.7.
    case = load_labeled_case(path)
    assert case.case_id


def test_corpus_has_all_seven_scenario_labels() -> None:
    labels = set()
    for path in CASE_FILES:
        raw = json.loads(path.read_text(encoding="utf-8"))
        labels.add(raw["label"])
    assert labels == {
        "compliant",
        "mandate_breaching",
        "broken_chain",
        "synthetic_identity",
        "structuring",
        "drift",
        "prompt_injection",
    }
