<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Assessment, ReportMeta, TopFix } from '$lib/types';

  interface Props {
    assessment: Assessment;
    meta: ReportMeta;
    sourceUrl: string;
    assessedAt: Date;
  }

  let { assessment, meta, sourceUrl, assessedAt }: Props = $props();
  const dispatch = createEventDispatcher<{ 'show-upgrade': void }>();

  const sectionSummaries = $derived([
    { key: 'photos', label: 'Photos', score: assessment.sectionScores.photos },
    { key: 'copy', label: 'Description', score: assessment.sectionScores.copy },
    { key: 'amenities', label: 'Amenities clarity', score: assessment.sectionScores.amenitiesClarity },
    { key: 'trust', label: 'Trust signals', score: assessment.sectionScores.trustSignals }
  ]);

  const assessedAtLabel = $derived.by(() => {
    if (!assessedAt) return '';
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      month: 'short',
      day: 'numeric'
    }).format(assessedAt);
  });

  const formatPercent = (value?: number | null, fractionDigits = 0) => {
    if (value === undefined || value === null) return '—';
    return `${value.toFixed(fractionDigits)}%`;
  };

  const impactLabel = {
    high: 'High impact',
    medium: 'Medium impact',
    low: 'Low impact'
  } as const;

  type FixSlot = { number: number; locked: true } | { number: number; locked: false; fix: TopFix };

  const reportBadgeLabel = $derived(meta.isPaid ? 'Paid report' : 'Free preview');
  const showBonusSummary = $derived(Boolean(meta.isPaid && assessment.bonusSummary));
  const showOwnerOverview = $derived(Boolean(meta.isPaid && assessment.ownerOverview));
  const topFixesLimited = $derived.by(() => assessment.topFixes.slice(0, 5));
  const hiddenFixCount = $derived.by(() => {
    if (meta.isPaid) return 0;
    return Math.min(meta.hiddenFixCount ?? 0, 3);
  });
  const fixSlots = $derived.by<FixSlot[]>(() => {
    const slots: FixSlot[] = [];
    const limitedFixes = topFixesLimited;

    if (meta.isPaid) {
      limitedFixes.forEach((fix, idx) => {
        slots.push({ number: idx + 1, locked: false, fix });
      });
      return slots;
    }

    const totalSlots = Math.min(5, hiddenFixCount + limitedFixes.length);
    for (let i = 0; i < totalSlots; i += 1) {
      if (i < hiddenFixCount) {
        slots.push({ number: i + 1, locked: true });
      } else {
        const fix = limitedFixes[i - hiddenFixCount];
        if (!fix) continue;
        slots.push({ number: i + 1, locked: false, fix });
      }
    }

    return slots;
  });
  const hasLockedFixes = $derived(fixSlots.some((slot) => slot.locked));

  const requestUpgrade = () => {
    dispatch('show-upgrade');
  };

  const coverageLabels: Record<string, string> = {
    bedroom: 'Bedroom',
    bath: 'Bathroom',
    kitchen: 'Kitchen',
    living: 'Living area',
    exterior_day: 'Exterior (day)',
    exterior_night: 'Exterior (night)'
  };

  const formatCoverageList = (keys: string[]) =>
    keys.map((key) => coverageLabels[key] ?? key).join(', ');

  const describeGalleryDepth = (count: number) => {
    if (count >= 18) return `${count} photos - robust coverage`;
    if (count >= 12) return `${count} photos - balanced gallery`;
    if (count >= 8) return `${count} photos - basic variety`;
    if (count >= 5) return `${count} photos - needs more variety`;
    if (count > 0) return `${count} photos - very limited`;
    return 'No photos detected';
  };

  const describeReviewSummary = (count: number) => {
    if (count >= 4) return `${count} excerpts surfaced - strong social proof`;
    if (count >= 2) return `${count} excerpts surfaced - solid trust anchor`;
    if (count === 1) return '1 excerpt surfaced - consider adding another';
    return 'No review snippets available';
  };

  const describeHouseRules = (hasRules: boolean, ruleCount: number) => {
    if (!hasRules) return 'Not published';
    if (ruleCount >= 6) return `${ruleCount} items - thorough expectations`;
    if (ruleCount >= 3) return `${ruleCount} items - concise guidance`;
    return `${ruleCount} item - add a bit more detail`;
  };

  const describeSummaryPresence = (hasSummary: boolean, length: number) => {
    if (!hasSummary) return 'Missing summary blurb';
    if (length >= 160) return 'Present - detailed teaser';
    if (length >= 80) return 'Present - balanced intro';
    return 'Present - could add more context';
  };

  const describeDescriptionLength = (length: number) => {
    if (length >= 800) return `${length} characters - comprehensive`;
    if (length >= 500) return `${length} characters - informative`;
    if (length >= 300) return `${length} characters - skimpy`;
    if (length > 0) return `${length} characters - very short`;
    return 'No description captured';
  };
</script>

<section class="results">
  <header class="results__header">
    <div>
      <p class="eyebrow">Assessment complete</p>
      <h2>Overall score: <span>{assessment.overall}%</span></h2>
      <div class="report-badges">
        <span class:paid={meta.isPaid} class="report-badge">{reportBadgeLabel}</span>
        {#if meta.isPaid && meta.creditId}
          <span class="report-badge secondary">Credit redeemed</span>
        {/if}
      </div>
    </div>
    <div class="meta">
      <a href={sourceUrl} rel="noreferrer" target="_blank">View listing ↗</a>
      <span aria-label="Assessed at">{assessedAtLabel}</span>
      {#if !meta.isPaid}
        <button type="button" class="header-upgrade" onclick={requestUpgrade}>
          Buy full report
        </button>
      {/if}
    </div>
  </header>

  {#if showOwnerOverview && assessment.ownerOverview}
    <section class="overview">
      <h3>Coach's overview</h3>
      <p>{assessment.ownerOverview}</p>
    </section>
  {/if}

  {#if showBonusSummary && assessment.bonusSummary}
    <section class="bonus">
      <h3>Bonus next steps</h3>
      <p>{assessment.bonusSummary}</p>
    </section>
  {/if}

  <div class="score-grid">
    {#each sectionSummaries as section (section.key)}
      <article class="score-card">
        <h3>{section.label}</h3>
        <div class="score-bar" aria-label={`${section.label} score ${section.score} out of 100`}>
          <div class="score-bar__fill" style={`--progress: ${section.score};`}></div>
        </div>
        <span class="score-card__value">{section.score}%</span>
      </article>
    {/each}
  </div>

  <div class="stat-grid" role="list">
    <article class="stat-card" role="listitem">
      <header>
        <h3>Photo coverage</h3>
        <span class="badge">{assessment.photoStats.count} photos</span>
      </header>
      <dl>
        <div>
          <dt>Gallery depth</dt>
          <dd>
            {describeGalleryDepth(assessment.photoStats.count)}
            <span class="metric-note">More variety helps guests visualize the stay before booking.</span>
          </dd>
        </div>
        {#if assessment.photoStats.keySpaceMetricsSupported && assessment.photoStats.keySpacesTotal > 0}
          <div>
            <dt>Key spaces covered</dt>
            <dd>
              {assessment.photoStats.keySpacesCovered} of {assessment.photoStats.keySpacesTotal}
              {#if assessment.photoStats.missingCoverage.length}
                &nbsp;(missing {formatCoverageList(assessment.photoStats.missingCoverage)})
              {/if}
              <span class="metric-note">Core rooms like bedrooms and baths should always appear in the gallery.</span>
            </dd>
          </div>
        {/if}
        <div>
          <dt>Coverage highlights</dt>
          <dd>
            {#if assessment.photoStats.coverage.length}
              {formatCoverageList(assessment.photoStats.coverage)}
            {:else}
              Limited signals detected.
            {/if}
            <span class="metric-note">Detected tags hint at which spaces or moments you're already showcasing.</span>
          </dd>
        </div>
        <div>
          <dt>Night exterior</dt>
          <dd>
            {assessment.photoStats.hasExteriorNight ? 'Included' : 'Missing'}
            <span class="metric-note">Night shots reassure late arrivals about lighting, access, and curb appeal.</span>
          </dd>
        </div>
        <div>
          <dt>Caption coverage</dt>
          <dd>
            {assessment.photoStats.altTextRatio !== null && assessment.photoStats.altTextRatio !== undefined
              ? formatPercent(assessment.photoStats.altTextRatio * 100, 0)
              : '—'}
            <span class="metric-note">Short captions help guests understand each shot and improve accessibility.</span>
          </dd>
        </div>
      </dl>
    </article>

    <article class="stat-card" role="listitem">
      <header>
        <h3>Description quality</h3>
        <span class="badge neutral">{assessment.copyStats.wordCount} words</span>
      </header>
      <dl>
        <div>
          <dt>Flesch readability</dt>
          <dd>
            {assessment.copyStats.flesch !== null && assessment.copyStats.flesch !== undefined
              ? assessment.copyStats.flesch.toFixed(1)
              : '—'}
            <span class="metric-note">Scores between 60-80 read quickly and keep skimmers engaged.</span>
          </dd>
        </div>
        <div>
          <dt>Second-person voice</dt>
          <dd>
            {assessment.copyStats.secondPersonPct !== null && assessment.copyStats.secondPersonPct !== undefined
              ? formatPercent(assessment.copyStats.secondPersonPct, 1)
              : '—'}
            <span class="metric-note">Aim for 1-3% "you" language to keep the description inviting without sounding forced.</span>
          </dd>
        </div>
        <div>
          <dt>Structured sections</dt>
          <dd>
            {assessment.copyStats.hasSections ? 'Yes' : 'No'}
            <span class="metric-note">Chunked headings make it easy to scan essentials like access and policies.</span>
          </dd>
        </div>
      </dl>
    </article>

    <article class="stat-card" role="listitem">
      <header>
        <div>
          <h3>Amenities audit</h3>
          <p class="heading-note">We cross-check Airbnb's amenity list against your description, reviews, and photos.</p>
        </div>
        <span class="badge accent">{assessment.amenities.listed.length} listed</span>
      </header>
      <dl>
        <div>
          <dt>Text evidence</dt>
          <dd>
            {#if assessment.amenities.textHits.length}
              {assessment.amenities.textHits.join(', ')}
            {:else}
              No strong confirmations.
            {/if}
          </dd>
        </div>
        <div>
          <dt>Likely present, not listed</dt>
          <dd>
            {#if assessment.amenities.likelyPresentNotListed.length}
              {assessment.amenities.likelyPresentNotListed.join(', ')}
            {:else}
              None detected.
            {/if}
          </dd>
        </div>
        <div>
          <dt>Listed without evidence</dt>
          <dd>
            {#if assessment.amenities.listedNoTextEvidence.length}
              {assessment.amenities.listedNoTextEvidence.join(', ')}
            {:else}
              All listings supported.
            {/if}
          </dd>
        </div>
      </dl>
    </article>

    <article class="stat-card" role="listitem">
      <header>
        <h3>Trust signals</h3>
        <span class="badge trust">{assessment.trustSignals.reviewCount} snippets</span>
      </header>
      <dl>
        <div>
          <dt>Guest sentiment</dt>
          <dd>
            {describeReviewSummary(assessment.trustSignals.reviewCount)}
            {#if assessment.trustSignals.reviewSnippets.length}
              <ul class="snippet-list">
                {#each assessment.trustSignals.reviewSnippets as snippet, idx (idx)}
                  <li>"{snippet}"</li>
                {/each}
              </ul>
            {/if}
            <span class="metric-note">Short quotes build credibility faster than star ratings alone.</span>
          </dd>
        </div>
        <div>
          <dt>House rules surfaced</dt>
          <dd>
            {describeHouseRules(assessment.trustSignals.hasHouseRules, assessment.trustSignals.houseRuleCount)}
            <span class="metric-note">Clear rules prevent surprises and signal that you run a professional stay.</span>
          </dd>
        </div>
        <div>
          <dt>Listing summary</dt>
          <dd>
            {describeSummaryPresence(assessment.trustSignals.hasSummary, assessment.trustSignals.summaryLength)}
            <span class="metric-note">A strong first paragraph hooks attention in search results and previews.</span>
          </dd>
        </div>
        <div>
          <dt>Description depth</dt>
          <dd>
            {describeDescriptionLength(assessment.trustSignals.descriptionLength)}
            <span class="metric-note">Rich detail answers guest questions before they reach out.</span>
          </dd>
        </div>
      </dl>
    </article>
  </div>

  <section aria-labelledby="top-fixes" class="fixes">
    <header>
      <h3 id="top-fixes">Top fixes</h3>
      <p>Focus on the high-impact opportunities to raise booking conversion.</p>
    </header>

    {#if fixSlots.length === 0}
      <p class="empty-state">No top fixes were suggested for this assessment.</p>
    {:else}
      <ol>
        {#each fixSlots as slot (slot.number)}
          {#if slot.locked}
            <li class="locked">
              <button type="button" class="locked-trigger" onclick={requestUpgrade}>
                <span class="skeleton-pill" aria-hidden="true"></span>
                <h4>{slot.number}. Unlock to reveal</h4>
                <span class="skeleton-bar" aria-hidden="true"></span>
                <span class="skeleton-bar short" aria-hidden="true"></span>
                <span class="locked-caption">Upgrade for the full action plan.</span>
              </button>
            </li>
          {:else if slot.fix}
            <li>
              <span class={`impact impact-${slot.fix.impact}`}>{impactLabel[slot.fix.impact]}</span>
              <h4>{slot.number}. {slot.fix.reason}</h4>
              <p>{slot.fix.howToFix}</p>
            </li>
          {/if}
        {/each}
      </ol>
      {#if hasLockedFixes}
        <div class="locked-actions">
          <button type="button" class="locked-primary" onclick={requestUpgrade}>Unlock all fixes</button>
        </div>
      {/if}
    {/if}
  </section>
</section>

<style>
  .results {
    display: grid;
    gap: 1.75rem;
    margin-top: 2.5rem;
  }

  .results__header {
    display: grid;
    gap: 1rem;
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.8), rgba(56, 189, 248, 0.55));
    border-radius: 18px;
    padding: 1.6rem 1.8rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    box-shadow: 0 25px 50px -30px rgba(30, 64, 175, 0.8);
  }

  .eyebrow {
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.18em;
    margin-bottom: 0.6rem;
    opacity: 0.8;
  }

  .results__header h2 {
    font-size: clamp(1.7rem, 4vw, 2.4rem);
    margin: 0;
    font-weight: 600;
  }

  .results__header h2 span {
    font-weight: 700;
  }

  .report-badges {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .report-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.78rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.3rem 0.7rem;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.12);
    color: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(15, 23, 42, 0.25);
  }

  .report-badge.paid {
    background: rgba(15, 23, 42, 0.7);
    color: rgba(248, 250, 252, 0.92);
    border-color: rgba(248, 250, 252, 0.4);
  }

  .report-badge.secondary {
    background: rgba(15, 118, 110, 0.18);
    color: rgba(13, 148, 136, 0.9);
    border-color: rgba(45, 212, 191, 0.25);
  }

  .meta {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.95rem;
    align-items: flex-end;
  }

  .meta a {
    color: #0f172a;
    font-weight: 600;
    text-decoration: none;
    background: rgba(248, 250, 252, 0.85);
    padding: 0.45rem 0.8rem;
    border-radius: 999px;
    transition: background 0.15s ease;
  }

  .meta a:hover,
  .meta a:focus-visible {
    background: rgba(248, 250, 252, 1);
  }

  .header-upgrade {
    border: none;
    border-radius: 999px;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: rgba(15, 23, 42, 0.92);
    font-weight: 600;
    font-size: 0.85rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 0.45rem 0.9rem;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  .header-upgrade:hover,
  .header-upgrade:focus-visible {
    transform: translateY(-1px);
    box-shadow: 0 14px 35px -24px rgba(37, 99, 235, 0.85);
  }

  .score-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
  }

  .score-card {
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    display: grid;
    gap: 0.8rem;
  }

  .bonus {
    background: rgba(22, 163, 74, 0.12);
    border: 1px solid rgba(134, 239, 172, 0.4);
    color: rgba(220, 252, 231, 0.92);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    display: grid;
    gap: 0.6rem;
  }

  .bonus h3 {
    margin: 0;
    font-size: 1.05rem;
    letter-spacing: 0.01em;
  }

  .overview {
    background: rgba(37, 99, 235, 0.12);
    border: 1px solid rgba(59, 130, 246, 0.4);
    color: rgba(226, 232, 240, 0.95);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    display: grid;
    gap: 0.6rem;
  }

  .overview h3 {
    margin: 0;
    font-size: 1.05rem;
    letter-spacing: 0.01em;
  }

  .overview p {
    margin: 0;
    line-height: 1.5;
  }

  .score-card h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  .score-bar {
    position: relative;
    height: 0.55rem;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.18);
    overflow: hidden;
  }

  .score-bar__fill {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, rgba(37, 99, 235, 0.95), rgba(56, 189, 248, 0.85));
    width: calc(var(--progress, 0) * 1%);
    max-width: 100%;
    transition: width 0.35s ease;
  }

  .score-card__value {
    font-size: 1.6rem;
    font-weight: 700;
  }

  .stat-grid {
    display: grid;
    gap: 1.2rem;
  }

  @media (min-width: 640px) {
    .stat-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: start;
    }
  }

  .stat-card {
    background: rgba(15, 23, 42, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 18px;
    padding: 1.3rem 1.4rem;
    display: grid;
    gap: 0.9rem;
  }

  .stat-card header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem;
    margin-bottom: 0.4rem;
  }

  .badge {
    background: rgba(37, 99, 235, 0.2);
    color: rgba(148, 197, 255, 0.92);
    border-radius: 999px;
    font-size: 0.75rem;
    padding: 0.32rem 0.7rem;
  }

  .heading-note {
    margin: 0.35rem 0 0;
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.75);
  }

  .badge.neutral {
    background: rgba(139, 92, 246, 0.18);
    color: rgba(216, 180, 254, 0.95);
  }

  .badge.accent {
    background: rgba(34, 197, 94, 0.18);
    color: rgba(187, 247, 208, 0.95);
  }

  .badge.trust {
    background: rgba(236, 72, 153, 0.18);
    color: rgba(251, 207, 232, 0.95);
  }

  dl {
    display: grid;
    gap: 0.7rem;
    margin: 0;
  }

  dt {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    opacity: 0.65;
  }

  dd {
    margin: 0.2rem 0 0;
    line-height: 1.5;
    color: rgba(226, 232, 240, 0.92);
  }

  .metric-note {
    display: block;
    margin-top: 0.35rem;
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.75);
  }

  .snippet-list {
    margin: 0.6rem 0 0;
    padding-left: 1.1rem;
    display: grid;
    gap: 0.35rem;
    color: rgba(226, 232, 240, 0.85);
  }

  .fixes {
    background: rgba(15, 23, 42, 0.78);
    border-radius: 18px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 1.6rem 1.7rem 2rem;
    display: grid;
    gap: 1.2rem;
  }

  .fixes header h3 {
    margin: 0;
    font-size: 1.2rem;
  }

  .fixes header p {
    margin: 0.35rem 0 0;
    color: rgba(203, 213, 225, 0.88);
  }

  .fixes ol {
    counter-reset: fix;
    display: grid;
    gap: 1rem;
    margin: 0;
    padding-left: 1.4rem;
  }

  .fixes li {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    display: grid;
    gap: 0.4rem;
  }

  .fixes li.locked {
    background: rgba(15, 23, 42, 0.72);
    border-style: dashed;
    padding: 0;
  }

  .fixes h4 {
    margin: 0;
    font-size: 1rem;
  }

  .fixes li.locked h4 {
    color: rgba(148, 163, 184, 0.7);
  }

  .fixes p {
    margin: 0;
    color: rgba(203, 213, 225, 0.88);
    line-height: 1.55;
  }

  .locked-trigger {
    border: none;
    background: transparent;
    color: inherit;
    width: 100%;
    padding: 1.1rem 1.3rem;
    display: grid;
    gap: 0.5rem;
    text-align: left;
    cursor: pointer;
    border-radius: 14px;
    transition: background 0.15s ease, transform 0.15s ease;
  }

  .locked-trigger:hover,
  .locked-trigger:focus-visible {
    background: rgba(37, 99, 235, 0.12);
    transform: translateY(-1px);
  }

  .skeleton-pill {
    width: 120px;
    height: 0.85rem;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(71, 85, 105, 0.2), rgba(148, 163, 184, 0.35), rgba(71, 85, 105, 0.2));
    animation: shimmer 1.6s linear infinite;
    background-size: 200% 100%;
  }

  .skeleton-bar {
    height: 0.9rem;
    border-radius: 10px;
    background: linear-gradient(90deg, rgba(71, 85, 105, 0.18), rgba(148, 163, 184, 0.28), rgba(71, 85, 105, 0.18));
    animation: shimmer 1.6s linear infinite;
    background-size: 200% 100%;
  }

  .skeleton-bar.short {
    width: 75%;
  }

  .locked-caption {
    font-size: 0.85rem;
    color: rgba(191, 219, 254, 0.8);
  }

  .impact {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border-radius: 999px;
    padding: 0.25rem 0.6rem;
    font-weight: 600;
  }

  .impact-high {
    background: rgba(239, 68, 68, 0.18);
    color: rgba(254, 202, 202, 0.95);
  }

  .impact-medium {
    background: rgba(245, 158, 11, 0.18);
    color: rgba(254, 215, 170, 0.95);
  }

  .impact-low {
    background: rgba(59, 130, 246, 0.18);
    color: rgba(191, 219, 254, 0.95);
  }

  .empty-state {
    margin: 0;
    color: rgba(203, 213, 225, 0.75);
  }

  .locked-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .locked-primary {
    border: none;
    border-radius: 12px;
    background: linear-gradient(135deg, #16a34a, #22d3ee);
    color: #0f172a;
    font-weight: 600;
    padding: 0.75rem 1.2rem;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  .locked-primary:hover,
  .locked-primary:focus-visible {
    transform: translateY(-1px);
    box-shadow: 0 16px 35px -24px rgba(13, 148, 136, 0.85);
  }

  @media (max-width: 900px) {
    .results__header {
      flex-direction: column;
      align-items: flex-start;
    }

    .meta {
      align-items: flex-start;
    }
  }

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }

  @media (max-width: 600px) {
    .results__header {
      padding: 1.4rem 1.5rem;
    }

    .meta a {
      font-size: 0.85rem;
    }
  }
</style>
