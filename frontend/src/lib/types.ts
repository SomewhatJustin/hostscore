export type ImpactLevel = 'high' | 'medium' | 'low';

export interface SectionScores {
  photos: number;
  copy: number;
  amenitiesClarity: number;
  trustSignals: number;
}

export interface PhotoStats {
  count: number;
  coverage: string[];
  missingCoverage: string[];
  keySpacesCovered: number;
  keySpacesTotal: number;
  hasExteriorNight: boolean;
  altTextRatio?: number | null;
  usesLegacyGallery: boolean;
  keySpaceMetricsSupported: boolean;
}

export interface TrustSignals {
  reviewCount: number;
  reviewSnippets: string[];
  hasHouseRules: boolean;
  houseRuleCount: number;
  hasSummary: boolean;
  summaryLength: number;
  descriptionLength: number;
}

export interface CopyStats {
  wordCount: number;
  flesch?: number | null;
  secondPersonPct?: number | null;
  hasSections: boolean;
}

export interface AmenityAudit {
  listed: string[];
  textHits: string[];
  likelyPresentNotListed: string[];
  listedNoTextEvidence: string[];
}

export interface TopFix {
  impact: ImpactLevel;
  reason: string;
  howToFix: string;
}

export interface Assessment {
  overall: number;
  sectionScores: SectionScores;
  photoStats: PhotoStats;
  copyStats: CopyStats;
  trustSignals: TrustSignals;
  amenities: AmenityAudit;
  topFixes: TopFix[];
}

export interface AssessmentPayload {
  url: string;
  force?: boolean;
}

export interface AssessmentError {
  status: number;
  message: string;
}
