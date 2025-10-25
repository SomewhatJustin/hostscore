from backend.api.extract import ListingContent, PhotoMeta
from backend.api.heuristics import run_heuristics, _score_photos


def test_score_photos_legacy_zero_key_spaces_and_alt_ratio():
    photos = [
        PhotoMeta(url="https://example.com/1.jpg", alt=""),
        PhotoMeta(url="https://example.com/2.jpg", alt=""),
    ]

    stats, score, recos = _score_photos(photos, uses_legacy_gallery=True)

    assert stats.uses_legacy_gallery is True
    assert stats.key_space_metrics_supported is False
    assert stats.key_spaces_covered == 0
    assert stats.key_spaces_total == 0
    assert stats.alt_text_ratio == 0.0
    assert score <= 100
    assert any("legacy layout" in fix.reason.lower() for fix in recos)


def test_run_heuristics_coerces_legacy_when_no_captions():
    content = ListingContent(
        url="https://example.com/listing",
        title="",
        summary="",
        description="",
        full_text="",
        photos=[
            PhotoMeta(url="https://example.com/1.jpg", alt=""),
            PhotoMeta(url="https://example.com/2.jpg", alt=""),
            PhotoMeta(url="https://example.com/3.jpg", alt=""),
        ],
        uses_legacy_gallery=False,
    )

    result = run_heuristics(content)

    stats = result.photo_stats
    assert stats.uses_legacy_gallery is True
    assert stats.key_space_metrics_supported is False
    assert stats.key_spaces_total == 0
    assert stats.alt_text_ratio == 0.0
