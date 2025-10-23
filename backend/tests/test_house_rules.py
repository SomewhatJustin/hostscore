from bs4 import BeautifulSoup

from backend.api.extract import ListingContent, _extract_house_rules
from backend.api.heuristics import _score_trust


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extract_house_rules_from_policies_section():
    html = """
    <section data-section-id="POLICIES_DEFAULT">
        <div class="outer">
            <div class="inner">
                <div class="heading">
                    <h3>House rules</h3>
                </div>
                <ul>
                    <li>No pets</li>
                    <li>No parties</li>
                    <li>No parties</li>
                </ul>
                <span>Check-out before 10am</span>
            </div>
        </div>
    </section>
    """
    soup = _soup(html)

    rules = _extract_house_rules(soup)

    assert rules == ["No pets", "No parties", "Check-out before 10am"]


def test_extract_house_rules_from_modal_dialog():
    html = """
    <div>
        <div role="dialog" aria-label="House rules">
            <div class="content">
                <span>No smoking</span>
                <button type="button">
                    <span>Show more</span>
                </button>
                <span>Quiet hours after 10pm</span>
            </div>
        </div>
    </div>
    """
    soup = _soup(html)

    rules = _extract_house_rules(soup)

    assert rules == ["No smoking", "Quiet hours after 10pm"]


def test_score_trust_marks_house_rules_when_present():
    content = ListingContent(
        url="https://example.test/listing",
        title="Cozy cabin",
        summary="Cozy retreat surrounded by trails.",
        description="Detailed description. " * 10,
        full_text="Full listing text. " * 10,
        house_rules=["No smoking", "Quiet hours after 10pm"],
    )

    stats, score, recommendations = _score_trust(content)

    assert stats.has_house_rules is True
    assert stats.house_rule_count == 2
    assert all("House rules not surfaced" not in fix.reason for fix in recommendations)
    assert score >= 70
