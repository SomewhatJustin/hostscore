<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { get } from 'svelte/store';

  import AssessmentForm from '$lib/components/AssessmentForm.svelte';
  import AssessmentResults from '$lib/components/AssessmentResults.svelte';
  import UpgradeDrawer from '$lib/components/UpgradeDrawer.svelte';
  import {
    assessListing,
    createCheckoutSession,
    requestMagicLink,
    fetchSession,
    confirmCheckout
  } from '$lib/api';
  import { sessionStore, setSession } from '$lib/session';
  import type { ReportEnvelope, SessionInfo, ReportType, AssessmentError } from '$lib/types';

  interface PageData {
    prefillUrl?: string;
  }

  let { data } = $props<{ data: PageData }>();
  const initialUrl = $derived(data?.prefillUrl ?? '');

  const loadingMessages = [
    'Inspecting your towels',
    'Seeing if a guest left anything',
    'Definitely NOT throwing a party',
    'Evaluating your listing',
    'Checking the vibe',
    'Asking to check-in early'
  ];

  let loading = $state(false);
  let loadingMessageIndex = $state(0);
  let error = $state<string | null>(null);
  let reportEnvelope = $state<ReportEnvelope | null>(null);
  let assessmentUrl = $state<string | null>(null);
  let assessedAt = $state<Date | null>(null);
  let controller = $state<AbortController | null>(null);
  let activeReportType = $state<ReportType>('free');
  let lastSubmission = $state<{ url: string; force: boolean } | null>(null);
  let session = $state<SessionInfo>(get(sessionStore));
  let upgradeStatus = $state<string | null>(null);
  let upgradeError = $state<string | null>(null);
  let upgradeLoading = $state(false);
  let upgradeDismissed = $state(false);
  let hasScrolledForUpgrade = $state(false);
  let upgradeScrollHandler: (() => void) | null = null;
  let loadingTimer: ReturnType<typeof setInterval> | null = null;
  let checkoutProcessing = $state(false);
  let checkoutMessage = $state<string | null>(null);
  let checkoutError = $state<string | null>(null);

  const dismissCheckoutNotice = () => {
    checkoutMessage = null;
    checkoutError = null;
  };

  const unsubscribe = sessionStore.subscribe((value) => {
    session = value;
  });

  onDestroy(() => {
    unsubscribe();
    controller?.abort();
    stopLoadingMessages();
    if (typeof window !== 'undefined' && upgradeScrollHandler) {
      window.removeEventListener('scroll', upgradeScrollHandler);
      upgradeScrollHandler = null;
    }
  });

  const startLoadingMessages = () => {
    loadingMessageIndex = 0;
    if (loadingTimer) {
      clearInterval(loadingTimer);
    }

    loadingTimer = setInterval(() => {
      loadingMessageIndex = (loadingMessageIndex + 1) % loadingMessages.length;
    }, 3000);
  };

  const stopLoadingMessages = () => {
    if (!loadingTimer) return;
    clearInterval(loadingTimer);
    loadingTimer = null;
  };

  const updateQueryParam = (urlValue: string) => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (urlValue) {
      params.set('url', urlValue);
    } else {
      params.delete('url');
    }
    const queryString = params.toString();
    const target = queryString ? `?${queryString}` : window.location.pathname;
    goto(target, { replaceState: true, noScroll: true, keepFocus: true });
  };

  const refreshSession = async () => {
    const refreshed = await fetchSession();
    session = refreshed;
    setSession(refreshed);
  };

  const clearCheckoutParam = () => {
    if (typeof window === 'undefined') return;
    const updated = new URL(window.location.href);
    updated.searchParams.delete('checkout_id');
    window.history.replaceState({}, '', updated.toString());
  };

  const setReportType = (mode: ReportType) => {
    activeReportType = mode;
    if (mode === 'free') {
      upgradeError = null;
      upgradeStatus = null;
    }
  };

  const ensurePaidReady = async (): Promise<boolean> => {
    if (!session.authenticated) {
      upgradeError = 'Sign in to run the paid report.';
      upgradeStatus = null;
      activeReportType = 'paid';
      return false;
    }

    if ((session.credits?.available ?? 0) <= 0) {
      upgradeError = 'You need at least one credit to run the paid report.';
      upgradeStatus = null;
      return false;
    }

    return true;
  };

  const startAssessment = async ({ url, force }: { url: string; force: boolean }) => {
    const sanitizedUrl = url.trim();
    if (!sanitizedUrl) return;

    lastSubmission = { url: sanitizedUrl, force };

    if (activeReportType === 'paid') {
      const ready = await ensurePaidReady();
      if (!ready) {
        return;
      }
    }

    controller?.abort();
    const nextController = new AbortController();
    controller = nextController;

    startLoadingMessages();
    loading = true;
    error = null;
    upgradeError = null;

    try {
      const result = await assessListing(
        { url: sanitizedUrl, reportType: activeReportType, force },
        nextController.signal
      );
      if (nextController.signal.aborted) return;

      upgradeDismissed = false;
      reportEnvelope = result;
      assessmentUrl = sanitizedUrl;
      assessedAt = new Date();
      updateQueryParam(sanitizedUrl);
      upgradeStatus = null;

      if (result.meta.isPaid) {
        await refreshSession();
      }
    } catch (err) {
      if (nextController.signal.aborted) return;

      if (typeof err === 'object' && err && 'message' in err) {
        const detail = err as AssessmentError;
        if ('status' in detail && detail.status === 302) {
          stopLoadingMessages();
          loading = false;
          goto('/not-enough-credits');
          return;
        }
        error = String(detail.message);
      } else {
        error = 'Unexpected error while assessing the listing.';
      }
    } finally {
      if (!nextController.signal.aborted) {
        stopLoadingMessages();
        loading = false;
      }
    }
  };

  const handleSubmit = (event: CustomEvent<{ url: string; force: boolean }>) => {
    setReportType('free');
    startAssessment(event.detail);
  };

  const handleMagicLink = async (event: CustomEvent<{ email: string }>) => {
    upgradeLoading = true;
    upgradeError = null;
    try {
      await requestMagicLink(event.detail.email);
      upgradeStatus = 'Magic link sent! Check your inbox within the next few minutes.';
    } catch (err) {
      upgradeError = err instanceof Error ? err.message : 'Unable to send magic link.';
    } finally {
      upgradeLoading = false;
    }
  };

  const handleCheckout = async () => {
    upgradeLoading = true;
    upgradeError = null;
    try {
      const { checkoutUrl } = await createCheckoutSession();
      window.location.href = checkoutUrl;
    } catch (err) {
      upgradeError = err instanceof Error ? err.message : 'Unable to start checkout.';
      upgradeLoading = false;
    }
  };

  const handleRunPaid = async () => {
    setReportType('paid');
    if (lastSubmission) {
      await startAssessment(lastSubmission);
    }
  };

  const handleShowUpgrade = () => {
    hasScrolledForUpgrade = true;
    upgradeDismissed = false;
  };

  const evaluateUpgradeScroll = () => {
    if (typeof window === 'undefined' || hasScrolledForUpgrade) return;
    const doc = document.documentElement;
    const scrollTop = window.scrollY || doc.scrollTop;
    const maxScroll = Math.max(doc.scrollHeight - window.innerHeight, 0);

    if (maxScroll <= 0) {
      if (scrollTop >= window.innerHeight * 0.5) {
        hasScrolledForUpgrade = true;
      }

      if (hasScrolledForUpgrade && upgradeScrollHandler) {
        window.removeEventListener('scroll', upgradeScrollHandler);
        upgradeScrollHandler = null;
      }
      return;
    }

    const progress = scrollTop / maxScroll;
    if (progress >= 0.5) {
      hasScrolledForUpgrade = true;
    }

    if (hasScrolledForUpgrade && upgradeScrollHandler) {
      window.removeEventListener('scroll', upgradeScrollHandler);
      upgradeScrollHandler = null;
    }
  };

  onMount(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const checkoutId = params.get('checkout_id');
      if (checkoutId) {
        checkoutProcessing = true;
        checkoutMessage = 'Finishing your purchase…';
        checkoutError = null;
        (async () => {
          try {
            const sessionInfo = await confirmCheckout(
              checkoutId,
              import.meta.env.DEV ? 'sandbox' : undefined
            );
            setSession(sessionInfo);
            session = sessionInfo;
            checkoutMessage = 'Payment confirmed! You now have an extra credit.';
            upgradeError = null;
            upgradeStatus = null;
            upgradeDismissed = true;
          } catch (err) {
            checkoutMessage = null;
            checkoutError = err instanceof Error
              ? err.message
              : 'Unable to verify checkout. Please try again or contact support.';
          } finally {
            checkoutProcessing = false;
            clearCheckoutParam();
          }
        })();
      }

      upgradeScrollHandler = () => evaluateUpgradeScroll();
      window.addEventListener('scroll', upgradeScrollHandler, { passive: true });
      evaluateUpgradeScroll();
    }

    if (initialUrl) {
      startAssessment({ url: initialUrl, force: false });
    }
  });

  const shouldShowUpgrade = $derived.by(() => {
    if (!reportEnvelope) return false;
    return !reportEnvelope.meta.isPaid && reportEnvelope.meta.hiddenFixCount > 0;
  });

  const shouldRevealUpgrade = $derived(shouldShowUpgrade && hasScrolledForUpgrade && !upgradeDismissed);

  const upgradeHiddenCount = $derived(
    reportEnvelope?.meta.hiddenFixCount ? Math.max(reportEnvelope.meta.hiddenFixCount, 1) : 8
  );

  const currentAssessment = $derived(reportEnvelope?.report ?? null);
</script>

{#if checkoutProcessing && checkoutMessage}
  <div class="checkout-banner loading" role="status" aria-live="assertive">
    <span class="inline-spinner" aria-hidden="true"></span>
    <span>{checkoutMessage}</span>
  </div>
{:else if checkoutMessage}
  <div class="checkout-banner success" role="status" aria-live="polite">
    <span>{checkoutMessage}</span>
    <button type="button" onclick={dismissCheckoutNotice} aria-label="Dismiss message">×</button>
  </div>
{:else if checkoutError}
  <div class="checkout-banner error" role="alert">
    <span>{checkoutError}</span>
    <button type="button" onclick={dismissCheckoutNotice} aria-label="Dismiss message">×</button>
  </div>
{/if}

<section class="hero">
  <div class="intro">
    <p class="kicker">HostScore assistant</p>
    <h1>Rate your Airbnb listing</h1>
    <p class="lede">
      Understand how travelers experience your Airbnb listing and get prioritized guidance to improve photos, storytelling, amenities, and trust signals before the next guest books.
    </p>
  </div>

  {#key initialUrl}
    <AssessmentForm
      initialUrl={initialUrl}
      loading={loading}
      mode={activeReportType}
      on:submit={handleSubmit}
    />
  {/key}

  {#if error}
    <div class="alert" role="status">
      <strong>Request failed:</strong> {error}
    </div>
  {/if}

  {#if currentAssessment && assessmentUrl && assessedAt && reportEnvelope}
    <AssessmentResults
      assessment={currentAssessment}
      assessedAt={assessedAt}
      sourceUrl={assessmentUrl}
      meta={reportEnvelope.meta}
      on:show-upgrade={handleShowUpgrade}
    />
  {/if}
</section>

{#if loading}
  <div class="loading-overlay" role="status" aria-live="assertive">
    <div class="loading-panel">
      <span class="overlay-spinner" aria-hidden="true"></span>
      <p>{loadingMessages[loadingMessageIndex]}</p>
    </div>
  </div>
{/if}

<UpgradeDrawer
  hiddenCount={upgradeHiddenCount}
  session={session}
  visible={shouldRevealUpgrade}
  loading={upgradeLoading}
  status={upgradeStatus}
  error={upgradeError}
  on:request-magic-link={handleMagicLink}
  on:start-checkout={handleCheckout}
  on:run-paid={handleRunPaid}
  on:dismiss={() => {
    upgradeDismissed = true;
  }}
/>

<style>
  .hero {
    display: grid;
    gap: 2rem;
    max-width: 980px;
    margin: 0 auto;
  }

  .intro {
    display: grid;
    gap: 0.8rem;
  }

  .kicker {
    text-transform: uppercase;
    font-size: 0.74rem;
    letter-spacing: 0.22em;
    color: rgba(148, 163, 184, 0.85);
    margin: 0;
  }

  h1 {
    font-size: clamp(2rem, 4vw, 2.8rem);
    margin: 0;
    font-weight: 700;
  }

  .lede {
    margin: 0;
    color: rgba(203, 213, 225, 0.92);
    font-size: 1.1rem;
    line-height: 1.65;
  }

  .checkout-banner {
    max-width: 980px;
    margin: 0 auto 1rem;
    padding: 0.85rem 1.1rem;
    border-radius: 14px;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.95rem;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.85);
    color: rgba(226, 232, 240, 0.95);
  }

  .checkout-banner.success {
    border-color: rgba(134, 239, 172, 0.4);
    background: rgba(16, 185, 129, 0.14);
    color: rgba(236, 253, 245, 0.95);
  }

  .checkout-banner.error {
    border-color: rgba(248, 113, 113, 0.45);
    background: rgba(239, 68, 68, 0.18);
    color: rgba(254, 226, 226, 0.95);
  }

  .checkout-banner button {
    margin-left: auto;
    background: transparent;
    border: none;
    color: inherit;
    font-size: 1.2rem;
    cursor: pointer;
    line-height: 1;
  }

  .checkout-banner button:hover,
  .checkout-banner button:focus-visible {
    opacity: 0.8;
  }

  .checkout-banner.loading {
    justify-content: flex-start;
  }

  .inline-spinner {
    width: 1rem;
    height: 1rem;
    border-radius: 999px;
    border: 2px solid rgba(148, 163, 184, 0.35);
    border-top-color: rgba(94, 234, 212, 0.9);
    animation: spin 0.75s linear infinite;
  }

  .alert {
    background: rgba(239, 68, 68, 0.18);
    border: 1px solid rgba(248, 113, 113, 0.45);
    color: rgba(254, 226, 226, 0.95);
    border-radius: 16px;
    padding: 1rem 1.2rem;
    font-size: 0.98rem;
    display: flex;
    gap: 0.6rem;
    align-items: center;
  }

  .loading-overlay {
    position: fixed;
    inset: 0;
    display: grid;
    place-items: center;
    backdrop-filter: blur(2px);
  }

  .loading-panel {
    background: rgba(15, 23, 42, 0.9);
    padding: 1.5rem 1.8rem;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    display: grid;
    gap: 0.75rem;
    align-items: center;
    justify-items: center;
    color: rgba(226, 232, 240, 0.95);
  }

  .overlay-spinner {
    width: 1.35rem;
    height: 1.35rem;
    border-radius: 999px;
    border: 3px solid rgba(148, 163, 184, 0.35);
    border-top-color: rgba(94, 234, 212, 0.9);
    animation: spin 0.75s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 640px) {
    .hero {
      gap: 1.5rem;
    }

    .loading-panel {
      width: min(90vw, 320px);
    }
  }
</style>
