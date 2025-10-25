from backend.api.heuristics import sort_top_fixes
from backend.api.models import TopFix


def test_sort_top_fixes_orders_by_impact_high_to_low():
    fixes = [
        TopFix(impact="medium", reason="B", how_to_fix=""),
        TopFix(impact="high", reason="A", how_to_fix=""),
        TopFix(impact="low", reason="C", how_to_fix=""),
        TopFix(impact="high", reason="A2", how_to_fix=""),
    ]

    ordered = sort_top_fixes(fixes)

    assert [fix.impact for fix in ordered] == ["high", "high", "medium", "low"]
    assert ordered[0].reason == "A"
    assert ordered[1].reason == "A2"
    assert ordered[2].reason == "B"
    assert ordered[3].reason == "C"
