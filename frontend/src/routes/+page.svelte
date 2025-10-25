<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { goto } from '$app/navigation';

  import AssessmentForm from '$lib/components/AssessmentForm.svelte';
  import AssessmentResults from '$lib/components/AssessmentResults.svelte';
  import { assessListing } from '$lib/api';
  import type { Assessment } from '$lib/types';

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
  let assessment = $state<Assessment | null>(null);
  let assessmentUrl = $state<string | null>(null);
  let assessedAt = $state<Date | null>(null);
  let controller = $state<AbortController | null>(null);
  let loadingTimer: ReturnType<typeof setInterval> | null = null;

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

  const startAssessment = async ({ url, force }: { url: string; force: boolean }) => {
    const sanitizedUrl = url.trim();
    if (!sanitizedUrl) return;

    controller?.abort();
    const nextController = new AbortController();
    controller = nextController;

    startLoadingMessages();
    loading = true;
    error = null;

    try {
      const result = await assessListing({ url: sanitizedUrl, force }, nextController.signal);
      if (nextController.signal.aborted) return;

      assessment = result;
      assessmentUrl = sanitizedUrl;
      assessedAt = new Date();
      updateQueryParam(sanitizedUrl);
    } catch (err) {
      if (nextController.signal.aborted) return;

      if (typeof err === 'object' && err && 'message' in err) {
        error = String(err.message);
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
    startAssessment(event.detail);
  };

  onMount(() => {
    if (initialUrl) {
      startAssessment({ url: initialUrl, force: false });
    }
  });

  onDestroy(() => {
    controller?.abort();
    stopLoadingMessages();
  });
</script>

<section class="hero">
  <div class="intro">
    <p class="kicker">HostScore assistant</p>
    <h1>Rate your Airbnb listing</h1>
    <p class="lede">
      Understand how travelers experience your Airbnb listing and get prioritized guidance to improve photos, storytelling, amenities, and trust signals before the next guest books.
    </p>
  </div>

  {#key initialUrl}
    <AssessmentForm initialUrl={initialUrl} loading={loading} on:submit={handleSubmit} />
  {/key}

  {#if error}
    <div class="alert" role="status">
      <strong>Request failed:</strong> {error}
    </div>
  {/if}

  {#if assessment && assessmentUrl && assessedAt}
    <AssessmentResults assessment={assessment} assessedAt={assessedAt} sourceUrl={assessmentUrl} />
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
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(6px);
    z-index: 1000;
  }

  .loading-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.5rem;
    padding: 2.8rem 3.2rem;
    border-radius: 24px;
    background: rgba(30, 41, 59, 0.92);
    box-shadow: 0 24px 48px rgba(15, 23, 42, 0.55);
    max-width: min(90vw, 420px);
    text-align: center;
  }

  .loading-panel p {
    margin: 0;
    font-size: 1.35rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    color: rgba(226, 232, 240, 0.96);
  }

  .overlay-spinner {
    width: 3rem;
    height: 3rem;
    border-radius: 999px;
    border: 4px solid rgba(148, 197, 255, 0.32);
    border-top-color: rgba(96, 165, 250, 0.9);
    animation: spin 0.85s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 768px) {
    .hero {
      gap: 1.75rem;
    }

    h1 {
      font-size: clamp(1.9rem, 6vw, 2.6rem);
    }
  }
</style>
