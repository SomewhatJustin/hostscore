<script lang="ts">
  import { onDestroy } from 'svelte';
  import { createCheckoutSession } from '$lib/api';
  import { sessionStore } from '$lib/session';
  import { get } from 'svelte/store';

  let session = $state(get(sessionStore));
  let loading = $state(false);
  let error = $state<string | null>(null);

  const unsubscribe = sessionStore.subscribe((value) => {
    session = value;
  });

  onDestroy(unsubscribe);

  const startCheckout = async () => {
    loading = true;
    error = null;
    try {
      const { checkoutUrl } = await createCheckoutSession();
      window.location.href = checkoutUrl;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unable to start checkout.';
      loading = false;
    }
  };
</script>

<section class="credits">
  <h1>Out of credits</h1>
  <p>
    Your paid report credits have been used. Purchase another credit to unlock the full assessment with all fixes,
    bonus insights, and next steps.
  </p>

  {#if error}
    <div class="alert">{error}</div>
  {/if}

  <div class="actions">
    <button type="button" onclick={startCheckout} disabled={loading}>
      {loading ? 'Redirecting…' : 'Buy another report'}
    </button>
    <a href="mailto:support@hostscore.com">Need help? Contact support</a>
  </div>

  {#if session.authenticated && session.credits}
    <p class="balance">
      Credits remaining: {session.credits.available}. Next credit expires
      {session.credits.nextExpiration ? new Date(session.credits.nextExpiration).toLocaleDateString() : 'soon'}.
    </p>
  {/if}
</section>

<style>
  .credits {
    max-width: 560px;
    margin: 4rem auto 0;
    display: grid;
    gap: 1.2rem;
  }

  h1 {
    margin: 0;
    font-size: clamp(2rem, 4vw, 2.6rem);
  }

  p {
    margin: 0;
    color: rgba(203, 213, 225, 0.88);
    line-height: 1.6;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
  }

  button {
    border: none;
    border-radius: 12px;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: #fff;
    font-weight: 600;
    padding: 0.85rem 1.4rem;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  button:hover,
  button:focus-visible {
    transform: translateY(-1px);
    box-shadow: 0 18px 35px -20px rgba(37, 99, 235, 0.9);
  }

  button:disabled {
    opacity: 0.65;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  a {
    color: rgba(165, 243, 252, 0.9);
    text-decoration: none;
  }

  a:hover,
  a:focus-visible {
    text-decoration: underline;
  }

  .alert {
    background: rgba(248, 113, 113, 0.15);
    border: 1px solid rgba(248, 113, 113, 0.3);
    color: rgba(254, 226, 226, 0.92);
    padding: 0.8rem 1rem;
    border-radius: 12px;
  }

  .balance {
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.85);
  }

  @media (max-width: 640px) {
    .credits {
      margin-top: 2.5rem;
    }

    .actions {
      flex-direction: column;
      align-items: stretch;
    }

    button {
      width: 100%;
    }
  }
</style>
