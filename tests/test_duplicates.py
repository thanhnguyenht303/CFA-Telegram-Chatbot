from __future__ import annotations

from cfa_vocab_bot.services.duplicate import find_duplicate, is_duplicate, normalize_term


def test_normalize_term_maps_common_aliases():
    assert normalize_term("Yield-to-Maturity") == "yield to maturity"
    assert normalize_term("YTM") == "yield to maturity"
    assert normalize_term("  operating   cash-flow ") == "operating cash flow"


def test_duplicate_detection_uses_aliases(session, seeded):
    duplicate = find_duplicate(session, "OCF", "Financial Statement Analysis")
    assert duplicate is not None
    assert duplicate.term == "Operating cash flow"
    assert is_duplicate(session, "revenue-recognition", "Financial Statement Analysis")

