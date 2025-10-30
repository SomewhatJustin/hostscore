export type ImpactLevel = 'high' | 'medium' | 'low';
export type ReportType = 'free' | 'paid';

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
  bonusSummary?: string | null;
  ownerOverview?: string | null;
}

export interface AssessmentPayload {
  url: string;
  reportType: ReportType;
  force?: boolean;
}

export interface AssessmentError {
  status: number;
  message: string;
}

export interface CreditSummary {
  available: number;
  nextExpiration?: string | null;
}

export interface ReportMeta {
  reportType: ReportType;
  isPaid: boolean;
  creditId?: string | null;
  hiddenFixCount: number;
  creditsRemaining?: number | null;
  nextCreditExpiration?: string | null;
}

export interface ReportEnvelope {
  report: Assessment;
  meta: ReportMeta;
}

export interface SessionInfo {
  authenticated: boolean;
  email?: string | null;
  credits?: CreditSummary;
}

export interface CheckoutSessionResult {
  checkoutId: string;
  checkoutUrl: string;
  environment?: 'live' | 'sandbox';
}
