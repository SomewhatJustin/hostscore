import { env } from '$env/dynamic/public';
import type {
  Assessment,
  AssessmentPayload,
  AssessmentError,
  AmenityAudit,
  CopyStats,
  PhotoStats,
  SectionScores,
  TopFix,
  TrustSignals
} from './types';

const API_BASE = env.PUBLIC_API_BASE?.replace(/\/+$/, '') ?? '';

interface RawSectionScores {
  photos: number;
  copy: number;
  amenities_clarity: number;
  trust_signals: number;
}

interface RawPhotoStats {
  count: number;
  coverage?: string[] | null;
  missing_coverage?: string[] | null;
  key_spaces_covered?: number | null;
  key_spaces_total?: number | null;
  has_exterior_night?: boolean | null;
  alt_text_ratio?: number | null;
}

interface RawCopyStats {
  word_count: number;
  flesch?: number | null;
  second_person_pct?: number | null;
  has_sections: boolean;
}

interface RawAmenityAudit {
  listed?: string[] | null;
  text_hits?: string[] | null;
  likely_present_not_listed?: string[] | null;
  listed_no_text_evidence?: string[] | null;
}

interface RawTopFix {
  impact?: 'high' | 'medium' | 'low';
  reason: string;
  how_to_fix: string;
}

interface RawTrustSignals {
  review_count?: number | null;
  review_snippets?: string[] | null;
  has_house_rules?: boolean | null;
  house_rule_count?: number | null;
  has_summary?: boolean | null;
  summary_length?: number | null;
  description_length?: number | null;
}

interface RawAssessmentResponse {
  overall: number;
  section_scores: RawSectionScores;
  photo_stats: RawPhotoStats;
  copy_stats: RawCopyStats;
  amenities: RawAmenityAudit;
  trust_signals: RawTrustSignals;
  top_fixes?: RawTopFix[];
}

const mapSectionScores = (scores: RawSectionScores): SectionScores => ({
  photos: scores.photos,
  copy: scores.copy,
  amenitiesClarity: scores.amenities_clarity,
  trustSignals: scores.trust_signals
});

const mapPhotoStats = (stats: RawPhotoStats): PhotoStats => ({
  count: stats.count,
  coverage: stats.coverage ?? [],
  missingCoverage: stats.missing_coverage ?? [],
  keySpacesCovered: stats.key_spaces_covered ?? 0,
  keySpacesTotal: stats.key_spaces_total ?? 5,
  hasExteriorNight: Boolean(stats.has_exterior_night),
  altTextRatio: typeof stats.alt_text_ratio === 'number' ? stats.alt_text_ratio : null
});

const mapCopyStats = (stats: RawCopyStats): CopyStats => ({
  wordCount: stats.word_count,
  flesch: stats.flesch ?? null,
  secondPersonPct: stats.second_person_pct ?? null,
  hasSections: stats.has_sections
});

const mapAmenityAudit = (audit: RawAmenityAudit): AmenityAudit => ({
  listed: audit.listed ?? [],
  textHits: audit.text_hits ?? [],
  likelyPresentNotListed: audit.likely_present_not_listed ?? [],
  listedNoTextEvidence: audit.listed_no_text_evidence ?? []
});

const mapTrustSignals = (signals: RawTrustSignals): TrustSignals => ({
  reviewCount: signals.review_count ?? 0,
  reviewSnippets: signals.review_snippets ?? [],
  hasHouseRules: Boolean(signals.has_house_rules),
  houseRuleCount: signals.house_rule_count ?? 0,
  hasSummary: Boolean(signals.has_summary),
  summaryLength: signals.summary_length ?? 0,
  descriptionLength: signals.description_length ?? 0
});

const mapTopFixes = (fixes: RawTopFix[] | undefined): TopFix[] =>
  (fixes ?? []).map((fix) => ({
    impact: fix.impact ?? 'medium',
    reason: fix.reason,
    howToFix: fix.how_to_fix
  }));

const mapAssessment = (payload: RawAssessmentResponse): Assessment => ({
  overall: payload.overall,
  sectionScores: mapSectionScores(payload.section_scores),
  photoStats: mapPhotoStats(payload.photo_stats),
  copyStats: mapCopyStats(payload.copy_stats),
  trustSignals: mapTrustSignals(payload.trust_signals),
  amenities: mapAmenityAudit(payload.amenities),
  topFixes: mapTopFixes(payload.top_fixes)
});

const withBase = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  if (!API_BASE) {
    return path;
  }

  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
};

export const assessListing = async (
  payload: AssessmentPayload,
  signal?: AbortSignal
): Promise<Assessment> => {
  const response = await fetch(withBase('/assess'), {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok) {
    let message = response.statusText || 'Failed to assess listing.';

    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') {
        message = body.detail;
      }
    } catch {
      // swallow JSON parse failure and use fallback message
    }

    const error: AssessmentError = {
      status: response.status,
      message
    };

    throw error;
  }

  const data: RawAssessmentResponse = await response.json();
  return mapAssessment(data);
};
