"""Utilities for matching scraped amenity tags against listing text."""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

from rapidfuzz import fuzz

try:  # Optional because model download can fail offline during development.
    from sentence_transformers import SentenceTransformer, util
except Exception:  # pragma: no cover - dependency may be absent in some environments.
    SentenceTransformer = None  # type: ignore
    util = None  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = os.getenv("AMENITY_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_NEGATION_PATTERNS = (
    "no",
    "without",
    "not included",
    "not available",
    "doesn t",
    "does not",
    "lacks",
    "lack of",
    "unavailable",
    "missing",
)

_AMENITY_ALIASES: Dict[str, List[str]] = {
    "air conditioning": ["ac", "a/c", "aircon", "climate control", "central air", "cooling"],
    "heating": ["central heat", "heat", "heater", "furnace"],
    "wifi": ["wi-fi", "wi fi", "internet", "wireless internet", "high speed internet"],
    "desk": ["workspace", "work desk", "office desk", "working area"],
    "parking": ["garage", "driveway parking", "free parking", "onsite parking"],
    "ev charger": ["electric vehicle charger", "ev charging", "car charger"],
    "hot tub": ["spa", "jacuzzi", "soaking tub"],
    "pool": ["swimming pool", "lap pool", "plunge pool"],
    "washer": ["washing machine", "laundry machine", "in suite laundry"],
    "dryer": ["clothes dryer", "tumble dryer"],
    "bbq grill": ["barbecue", "bbq", "barbeque grill"],
    "fireplace": ["indoor fireplace", "wood stove", "fire pit"],
    "patio": ["terrace", "deck", "outdoor seating"],
    "balcony": ["veranda", "lanai"],
    "smart tv": ["streaming tv", "roku tv", "apple tv"],
    "crib": ["cot", "pack and play"],
    "coffee maker": ["espresso machine", "coffee machine", "keurig"],
    "gym": ["fitness room", "exercise room", "fitness center"],
    "beach access": ["walk to beach", "steps to beach"],
}


def detect_amenity_mentions(tags: Sequence[str], text: str, *, similarity_threshold: float = 0.6) -> Tuple[List[str], List[str]]:
    """Return tags with and without textual evidence in ``text``.

    The detection pipeline walks through aliases, fuzzy matching, and
    embedding similarity to decide whether a listed amenity appears in
    the property description.
    """

    if not tags:
        return [], []

    sentences = _split_sentences(text)
    if not sentences:
        sentences = [text]
    normalized_sentences = [_normalize_for_window(sentence) for sentence in sentences]
    sentence_embeddings = _encode_sentences(sentences)

    present: List[str] = []
    missing: List[str] = []

    for original_tag in tags:
        canonical = _canonicalize(original_tag)
        alias_candidates = _aliases_for(canonical)
        if _has_direct_alias_hit(alias_candidates, sentences, normalized_sentences):
            present.append(original_tag)
            continue

        if _has_fuzzy_hit(alias_candidates, normalized_sentences):
            present.append(original_tag)
            continue

        if sentence_embeddings is not None and _has_embedding_hit(
            alias_candidates, sentences, sentence_embeddings, similarity_threshold
        ):
            present.append(original_tag)
            continue

        missing.append(original_tag)

    return present, missing


def _canonicalize(value: str) -> str:
    trimmed = value.strip().lower()
    trimmed = re.sub(r"\s+", " ", trimmed)
    return trimmed


def _aliases_for(tag: str) -> List[str]:
    aliases = set()
    if tag:
        aliases.add(tag)
    base = re.sub(r"\s*\(.*?\)", "", tag).strip()
    if base:
        aliases.add(base)
    pieces = re.split(r"[/,&]", tag)
    for piece in pieces:
        piece = piece.strip()
        if piece:
            aliases.add(piece)
    for alias in _AMENITY_ALIASES.get(tag, []):
        cleaned = _canonicalize(alias)
        if cleaned:
            aliases.add(cleaned)
    return sorted(aliases)


def _normalize_for_window(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("/", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    normalized = text.replace("\n", " ")
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences


def _has_direct_alias_hit(
    aliases: Sequence[str],
    sentences: Sequence[str],
    normalized_sentences: Sequence[str],
) -> bool:
    for sentence, normalized in zip(sentences, normalized_sentences):
        if not normalized:
            continue
        padded = f" {normalized} "
        for alias in aliases:
            alias_norm = _normalize_for_window(alias)
            if not alias_norm:
                continue
            if f" {alias_norm} " in padded and not _is_negated(normalized, alias_norm):
                return True
    return False


def _has_fuzzy_hit(aliases: Sequence[str], normalized_sentences: Sequence[str]) -> bool:
    for normalized_sentence in normalized_sentences:
        if not normalized_sentence or _contains_negation(normalized_sentence):
            continue
        for alias in aliases:
            alias_norm = _normalize_for_window(alias)
            if not alias_norm:
                continue
            score = fuzz.WRatio(alias_norm, normalized_sentence)
            if score >= 90:
                return True
    return False


def _has_embedding_hit(
    aliases: Sequence[str],
    sentences: Sequence[str],
    sentence_embeddings,
    threshold: float,
) -> bool:
    model = _get_model()
    if model is None or util is None:
        return False
    alias_texts = [alias for alias in aliases if alias]
    if not alias_texts:
        return False
    alias_embeddings = _encode_aliases(tuple(alias_texts))
    if alias_embeddings is None:
        return False
    scores = util.cos_sim(alias_embeddings, sentence_embeddings)
    max_value = scores.max().item()
    if max_value < threshold:
        return False
    index = int(scores.argmax().item())
    sentence_index = index % scores.shape[1]
    sentence = _normalize_for_window(sentences[sentence_index])
    if _contains_negation(sentence):
        return False
    return True


def _is_negated(normalized_sentence: str, alias: str, window_words: int = 5) -> bool:
    if alias not in normalized_sentence:
        return False
    words = normalized_sentence.split()
    alias_words = alias.split()
    alias_len = len(alias_words)
    for idx in range(len(words) - alias_len + 1):
        if words[idx : idx + alias_len] == alias_words:
            window_start = max(0, idx - window_words)
            window_end = min(len(words), idx + alias_len + window_words)
            snippet = " ".join(words[window_start:window_end])
            if _contains_negation(snippet):
                return True
    return False


def _contains_negation(normalized_text: str) -> bool:
    padded = f" {normalized_text} "
    for neg in _NEGATION_PATTERNS:
        needle = neg.strip()
        if not needle:
            continue
        if f" {needle} " in padded:
            return True
    return False


@lru_cache(maxsize=1)
def _get_model():
    if SentenceTransformer is None:
        logger.warning("SentenceTransformer not available; amenity embedding checks disabled.")
        return None
    try:
        return SentenceTransformer(DEFAULT_MODEL_NAME)
    except Exception as exc:  # pragma: no cover - depends on runtime env
        logger.warning("Failed to load embedding model %s: %s", DEFAULT_MODEL_NAME, exc)
        return None


def _encode_sentences(sentences: Sequence[str]):
    model = _get_model()
    if model is None:
        return None
    if not sentences:
        return None
    try:
        return model.encode(list(sentences), normalize_embeddings=True, show_progress_bar=False)
    except Exception as exc:  # pragma: no cover - guard against runtime errors
        logger.warning("Failed to encode sentences: %s", exc)
        return None


@lru_cache(maxsize=256)
def _encode_aliases(aliases: Tuple[str, ...]):
    model = _get_model()
    if model is None:
        return None
    try:
        return model.encode(list(aliases), normalize_embeddings=True, show_progress_bar=False)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to encode amenity aliases %s: %s", aliases, exc)
        return None
