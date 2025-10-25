"""Deterministic heuristics for scoring Airbnb listings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean
from typing import List, Pattern, Set

from textstat import textstat

from .amenity_matcher import detect_amenity_mentions
from .extract import ListingContent, PhotoMeta
from .models import AmenityAudit, CopyStats, PhotoStats, SectionScores, TopFix, TrustSignals

_IMPACT_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def sort_top_fixes(fixes: List[TopFix]) -> List[TopFix]:
    """Order fixes by impact (high -> medium -> low)."""

    def rank(fix: TopFix) -> int:
        impact = getattr(fix.impact, "value", fix.impact)
        return _IMPACT_PRIORITY.get(str(impact), len(_IMPACT_PRIORITY))

    return sorted(fixes, key=rank)

_COVERAGE_KEYWORDS = {
    "bedroom": {"bedroom", "primary bedroom", "guest room", "bunk", "bed"},
    "bath": {"bathroom", "shower", "bath", "tub"},
    "kitchen": {"kitchen", "dining", "cook", "cookware", "stove", "oven"},
    "living": {"living room", "sofa", "lounge", "fireplace"},
    "exterior_day": {"exterior", "patio", "balcony", "yard", "terrace", "porch", "deck"},
    "exterior_night": {"night", "evening", "sunset"},
}

_AMENITY_PATTERNS = {
    "desk": [r"\bworkspace\b", r"\bwork ?desk\b", r"\bdedicated desk\b", r"\boffice\b"],
    "parking": [r"\bparking\b", r"\bgarage\b", r"\bdriveway\b"],
    "wifi": [r"\bwi-?fi\b", r"\bwireless internet\b", r"\bhigh[- ]speed internet\b"],
    "air conditioning": [r"\bair conditioning\b", r"\bcentral air\b", r"\bclimate control\b", r"\ba/c\b"],
    "laundry": [r"\bwasher\b", r"\bdryer\b", r"\blaundry\b"],
}

_NEGATIVE_PREFIXES = [
    "no ",
    "without ",
    "not included",
    "not available",
    "doesn't",
    "does not",
    "lack of",
    "unavailable",
]

_AMENITY_REGEX = {
    name: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for name, patterns in _AMENITY_PATTERNS.items()
}


@dataclass
class HeuristicResult:
    """Container for deterministic scoring results."""

    overall: int
    section_scores: SectionScores
    photo_stats: PhotoStats
    copy_stats: CopyStats
    amenities: AmenityAudit
    trust_stats: TrustSignals
    recommendations: List[TopFix] = field(default_factory=list)


_LEGACY_IMAGE_LABEL = re.compile(r"\b(?:listing\s+)?image\s*\d+(?:\s+of\s+\d+)?$", re.I)


def _coerce_legacy_gallery_flag(photos: List[PhotoMeta], uses_legacy_gallery: bool) -> bool:
    """Fallback detection for legacy galleries when HTML markers are missing."""
    if uses_legacy_gallery:
        return True
    if not photos:
        return False
    generic_count = 0
    for photo in photos:
        alt = (photo.alt or "").strip()
        if not alt:
            generic_count += 1
            continue
        if _LEGACY_IMAGE_LABEL.search(alt):
            generic_count += 1
    return generic_count >= max(3, len(photos))


def run_heuristics(content: ListingContent) -> HeuristicResult:
    """Compute deterministic metrics for a listing."""
    uses_legacy_gallery = _coerce_legacy_gallery_flag(
        content.photos, content.uses_legacy_gallery
    )
    photo_stats, photo_score, photo_recos = _score_photos(
        content.photos, uses_legacy_gallery
    )
    copy_stats, copy_score, copy_recos = _score_copy(content)
    amenities_audit, amenity_score, amenity_recos = _score_amenities(content)
    trust_stats, trust_score, trust_recos = _score_trust(content)

    section_scores = SectionScores(
        photos=photo_score,
        copy=copy_score,
        amenities_clarity=amenity_score,
        trust_signals=trust_score,
    )
    overall = int(round(mean(section_scores.model_dump().values())))
    combined_recos = photo_recos + copy_recos + amenity_recos + trust_recos
    top_recos = sort_top_fixes(combined_recos)[:5]

    return HeuristicResult(
        overall=overall,
        section_scores=section_scores,
        photo_stats=photo_stats,
        copy_stats=copy_stats,
        amenities=amenities_audit,
        trust_stats=trust_stats,
        recommendations=top_recos,
    )


def _score_photos(photos: List[PhotoMeta], uses_legacy_gallery: bool = False):
    count = len(photos)
    unique_urls = {photo.url for photo in photos if photo.url}
    near_duplicate_ratio = (
        (count - len(unique_urls)) / count if count and len(unique_urls) else None
    )
    coverage = _infer_coverage(photos) if not uses_legacy_gallery else set()
    essential_keys = {"bedroom", "bath", "kitchen", "living", "exterior_day"}
    essential_coverage = coverage & essential_keys if not uses_legacy_gallery else set()
    missing_coverage = essential_keys - essential_coverage if not uses_legacy_gallery else set()
    alt_count = sum(1 for photo in photos if (photo.alt or "").strip())
    if not count:
        alt_text_ratio = None
    elif uses_legacy_gallery:
        alt_text_ratio = 0.0
    else:
        alt_text_ratio = alt_count / count

    score = 100
    recommendations: List[TopFix] = []

    if count < 5:
        score -= 45
        recommendations.append(
            TopFix(
                impact="high",
                reason="Too few gallery photos",
                how_to_fix="Upload at least 10 high-quality photos covering each room.",
            )
        )
    elif count < 10:
        score -= 25
        recommendations.append(
            TopFix(
                impact="high",
                reason="Limited gallery depth",
                how_to_fix="Aim for 12-15 photos to cover bedrooms, bathrooms, kitchen, and exterior.",
            )
        )

    if near_duplicate_ratio is not None and near_duplicate_ratio > 0.35:
        score -= 25
        recommendations.append(
            TopFix(
                impact="medium",
                reason="Gallery includes near-duplicate photos",
                how_to_fix="Swap repetitive angles for unique shots that show new details.",
            )
        )
    elif near_duplicate_ratio is not None and near_duplicate_ratio > 0.2:
        score -= 12

    if missing_coverage:
        score -= min(30, len(missing_coverage) * 6)
        recommendations.append(
            TopFix(
                impact="high",
                reason=f"Gallery missing: {', '.join(sorted(missing_coverage))}",
                how_to_fix="Add clear photos for each missing area to reassure guests.",
            )
        )

    score = max(0, min(100, score))

    key_spaces_supported = not uses_legacy_gallery

    if uses_legacy_gallery:
        recommendations.append(
            TopFix(
                impact="low",
                reason="Gallery uses Airbnb's legacy layout",
                how_to_fix=(
                    "Switch to Airbnb's newer room-by-room gallery so guests can explore each space in the guided tour."
                ),
            )
        )

    stats = PhotoStats(
        count=count,
        coverage=sorted(coverage),
        missing_coverage=sorted(missing_coverage),
        key_spaces_covered=len(essential_coverage) if key_spaces_supported else 0,
        key_spaces_total=len(essential_keys) if key_spaces_supported else 0,
        has_exterior_night="exterior_night" in coverage,
        alt_text_ratio=round(alt_text_ratio, 3) if alt_text_ratio is not None else None,
        uses_legacy_gallery=uses_legacy_gallery,
        key_space_metrics_supported=key_spaces_supported,
    )
    return stats, score, recommendations


def _infer_coverage(photos: List[PhotoMeta]) -> Set[str]:
    coverage: Set[str] = set()
    for photo in photos:
        text = (photo.alt or "").lower()
        for bucket, keywords in _COVERAGE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                coverage.add(bucket)
    return coverage


def _score_copy(content: ListingContent):
    description = content.description.strip() or content.full_text
    word_count = len(re.findall(r"\b\w+\b", description))

    try:
        flesch_score = textstat.flesch_reading_ease(description) if description else None
    except Exception:
        flesch_score = None

    sentences = [s.strip() for s in re.split(r"[.!?]\s+", description) if s.strip()]
    second_person_sentences = [
        sentence for sentence in sentences if re.search(r"\byou(r)?\b", sentence, re.I)
    ]
    second_person_pct = (
        len(second_person_sentences) / len(sentences) if sentences else 0.0
    )

    has_sections = bool(
        re.search(r"(^|\n)\s*(?:-|\d+\.)\s+\w+", description.lower())
        or "\n\n" in description
    )

    score = 100
    recommendations: List[TopFix] = []

    if word_count < 120:
        score -= 35
        recommendations.append(
            TopFix(
                impact="high",
                reason="Description is too short",
                how_to_fix="Expand the description to 200+ words covering layout, highlights, and nearby draws.",
            )
        )
    elif word_count < 180:
        score -= 15

    if flesch_score is not None:
        if flesch_score < 45:
            score -= 25
            recommendations.append(
                TopFix(
                    impact="medium",
                    reason="Copy is dense and hard to scan",
                    how_to_fix="Use shorter sentences and break long paragraphs into bullets.",
                )
            )
        elif flesch_score < 55:
            score -= 10

    if second_person_pct < 0.2:
        score -= 10
        recommendations.append(
            TopFix(
                impact="low",
                reason="Description rarely speaks to the guest",
                how_to_fix="Add lines that highlight benefits in second person (e.g., 'You'll love ...').",
            )
        )

    if not has_sections:
        score -= 8
        recommendations.append(
            TopFix(
                impact="medium",
                reason="Description lacks scannable sections",
                how_to_fix="Introduce short headings or bullet lists for rooms, amenities, and policies.",
            )
        )

    score = max(0, min(100, score))

    stats = CopyStats(
        word_count=word_count,
        flesch=round(flesch_score, 1) if flesch_score is not None else None,
        second_person_pct=round(second_person_pct * 100, 1),
        has_sections=has_sections,
    )
    return stats, score, recommendations


def _score_amenities(content: ListingContent):
    listed = [amenity.strip() for amenity in content.amenities_listed if amenity.strip()]
    normalized_listed = {_normalize_token(amenity): amenity for amenity in listed}
    listed_lower = [amenity.lower() for amenity in listed]

    text_corpus = " ".join(
        [
            content.title,
            content.summary,
            content.description,
            content.full_text,
            " ".join(content.house_rules),
            " ".join(content.reviews),
        ]
    )

    text_hits, listed_no_text = detect_amenity_mentions(listed, text_corpus)

    likely_present_not_listed: List[str] = []
    lowered_blob = text_corpus.lower()
    lowered_blob = re.sub(r"\s+", " ", lowered_blob)
    for amenity, patterns in _AMENITY_REGEX.items():
        token = _normalize_token(amenity)
        if token in normalized_listed:
            continue
        if any(pattern.search(name) for pattern in patterns for name in listed_lower):
            continue
        if _has_positive_reference(lowered_blob, patterns):
            likely_present_not_listed.append(amenity)

    score = 100
    recommendations: List[TopFix] = []

    if len(listed) < 10:
        score -= 25
        recommendations.append(
            TopFix(
                impact="high",
                reason="Too few amenities listed",
                how_to_fix="Audit and list at least 15 key amenities (wifi, parking, climate control, workspace).",
            )
        )
    elif len(listed) < 15:
        score -= 10

    if listed_no_text:
        score -= min(20, len(listed_no_text) * 3)
        recommendations.append(
            TopFix(
                impact="medium",
                reason="Amenities listed without supporting copy",
                how_to_fix="Work a short mention of each major amenity into the description to build trust.",
            )
        )

    if likely_present_not_listed:
        score -= 12
        recommendations.append(
            TopFix(
                impact="medium",
                reason="Amenities hinted at but not listed",
                how_to_fix=f"Add these amenities to the listing: {', '.join(likely_present_not_listed)}.",
            )
        )

    score = max(0, min(100, score))
    audit = AmenityAudit(
        listed=listed,
        text_hits=text_hits,
        likely_present_not_listed=likely_present_not_listed,
        listed_no_text_evidence=listed_no_text,
    )
    return audit, score, recommendations


def _score_trust(content: ListingContent):
    score = 100
    recommendations: List[TopFix] = []

    review_snippets = [snippet.strip() for snippet in content.reviews[:2] if snippet.strip()]
    review_count = len([snippet for snippet in content.reviews if snippet.strip()])

    if review_count == 0:
        score -= 30
        recommendations.append(
            TopFix(
                impact="medium",
                reason="Listing lacks visible review quotes",
                how_to_fix="Feature a couple of standout review snippets near the top of the description.",
            )
        )

    house_rule_entries = [rule.strip() for rule in content.house_rules if rule.strip()]
    house_rule_count = len(house_rule_entries)
    if house_rule_count == 0:
        score -= 20
        recommendations.append(
            TopFix(
                impact="medium",
                reason="House rules not surfaced",
                how_to_fix="Add a concise house rules section to set expectations (quiet hours, pets, etc.).",
            )
        )

    summary_text = content.summary.strip()
    description_text = content.description.strip()
    if not summary_text:
        score -= 10
    if len(description_text) < 120:
        score -= 10

    score = max(0, min(100, score))
    stats = TrustSignals(
        review_count=review_count,
        review_snippets=review_snippets,
        has_house_rules=house_rule_count > 0,
        house_rule_count=house_rule_count,
        has_summary=bool(summary_text),
        summary_length=len(summary_text),
        description_length=len(description_text),
    )
    return stats, score, recommendations


def _normalize_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9 ]+", "", value.lower())
    token = re.sub(r"\s+", " ", token).strip()
    return token


def _has_positive_reference(text: str, patterns: List[Pattern[str]]) -> bool:
    lowered = text.lower()
    for pattern in patterns:
        for match in pattern.finditer(lowered):
            start = match.start()
            end = match.end()
            prefix = lowered[max(0, start - 24) : start].strip()
            suffix = lowered[end : end + 16].strip()
            if any(prefix.endswith(cue.strip()) for cue in _NEGATIVE_PREFIXES):
                continue
            if suffix.startswith("not included") or suffix.startswith("not available"):
                continue
            return True
    return False
