<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SessionInfo } from '$lib/types';

  interface Props {
    hiddenCount: number;
    session: SessionInfo;
    visible: boolean;
    loading?: boolean;
    status?: string | null;
    error?: string | null;
  }

  const dispatch = createEventDispatcher<{
    'request-magic-link': { email: string };
    'start-checkout': void;
    'run-paid': void;
    dismiss: void;
  }>();

  let { hiddenCount, session, visible, loading = false, status = null, error = null }: Props = $props();
  let email = $state('');

  const handleSubmit = (event: SubmitEvent) => {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    dispatch('request-magic-link', { email: trimmed });
  };

  const startCheckout = () => {
    if (loading) return;
    dispatch('start-checkout');
  };

  const runPaid = () => {
    if (loading) return;
    dispatch('run-paid');
  };

  const dismiss = () => {
    dispatch('dismiss');
  };
</script>

{#if visible}
  <aside class="upgrade-drawer" role="status" aria-live="polite">
    <div class="content">
      <header>
        <button type="button" class="close-button" aria-label="Hide upgrade prompt" onclick={dismiss}>
          ×
        </button>
        <h3>Unlock {hiddenCount} more fixes + bonus insights</h3>
        <p>Upgrade to the paid report for a complete action plan and tailored next steps.</p>
      </header>

      {#if error}
        <div class="alert error">{error}</div>
      {/if}

      {#if !session.authenticated}
        {#if status}
          <div class="alert success">{status}</div>
        {:else}
          <form class="magic-link" onsubmit={handleSubmit}>
            <label for="upgrade-email">Email address</label>
            <div class="input-row">
              <input
                id="upgrade-email"
                type="email"
                placeholder="you@example.com"
                bind:value={email}
                required
                autocomplete="email"
                disabled={loading}
              />
            <button type="submit" disabled={loading}>
              {loading ? 'Sending…' : 'Email me a magic link'}
            </button>
          </div>
        </form>
      {/if}
        <p class="footnote">We’ll send a single-use link to sign in and unlock the full report.</p>
      {:else}
        {#if (session.credits?.available ?? 0) > 0}
          <div class="cta">
            <p>You have {session.credits?.available} credit{(session.credits?.available ?? 0) === 1 ? '' : 's'} remaining.</p>
            <button type="button" class="primary" disabled={loading} onclick={runPaid}>
              {loading ? 'Preparing…' : 'Run paid report'}
            </button>
          </div>
        {:else}
          <div class="cta">
            <p>Looks like you’re out of credits. Grab another to unlock the full insights.</p>
            <button type="button" disabled={loading} onclick={startCheckout}>
              {loading ? 'Redirecting…' : 'Buy another report'}
            </button>
          </div>
          <p class="support-note">Need help? Reach us at <a href="mailto:support@hostscore.com">support@hostscore.com</a>.</p>
        {/if}
      {/if}
    </div>
  </aside>
{/if}

<style>
  .upgrade-drawer {
    position: fixed;
    left: 50%;
    bottom: 1.5rem;
    transform: translateX(-50%);
    z-index: 50;
    width: min(680px, calc(100% - 2rem));
    background: linear-gradient(145deg, rgba(15, 23, 42, 0.95), rgba(37, 99, 235, 0.22));
    border: 1px solid rgba(148, 163, 184, 0.5);
    border-radius: 20px;
    box-shadow:
      0 28px 60px -28px rgba(37, 99, 235, 0.7),
      0 18px 38px -30px rgba(59, 130, 246, 0.65);
    padding: 1.6rem 1.9rem;
    backdrop-filter: blur(14px);
  }

  .content {
    display: grid;
    gap: 1rem;
  }

  header {
    position: relative;
    display: grid;
    gap: 0.35rem;
  }

  header h3 {
    margin: 0;
    font-size: 1.24rem;
  }

  header p {
    margin: 0;
    color: rgba(226, 232, 240, 0.85);
    font-size: 0.95rem;
  }

  .close-button {
    position: absolute;
    top: -0.6rem;
    right: -0.6rem;
    width: 2rem;
    height: 2rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.45);
    background: rgba(15, 23, 42, 0.92);
    color: rgba(226, 232, 240, 0.85);
    font-size: 1.3rem;
    line-height: 1;
    display: grid;
    place-items: center;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  }

  .close-button:hover,
  .close-button:focus-visible {
    transform: scale(1.05);
    box-shadow: 0 12px 35px -20px rgba(37, 99, 235, 0.8);
    background: rgba(30, 64, 175, 0.9);
  }

  .magic-link {
    display: grid;
    gap: 0.6rem;
  }

  .magic-link label {
    font-weight: 500;
    font-size: 0.9rem;
  }

  .input-row {
    display: flex;
    gap: 0.6rem;
  }

  input[type='email'] {
    flex: 1;
    padding: 0.75rem 1rem;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.92);
    color: #f8fafc;
  }

  input[type='email']:focus-visible {
    outline: none;
    border-color: rgba(59, 130, 246, 0.6);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
  }

  button:not(.close-button) {
    border: none;
    border-radius: 12px;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: #fff;
    font-weight: 600;
    padding: 0.75rem 1.2rem;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  button:not(.close-button):hover,
  button:not(.close-button):focus-visible {
    transform: translateY(-1px);
    box-shadow: 0 14px 35px -20px rgba(37, 99, 235, 0.9);
  }

  button:not(.close-button):disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .primary {
    background: linear-gradient(135deg, #16a34a, #22d3ee);
  }

  .footnote,
  .support-note {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(203, 213, 225, 0.7);
  }

  .alert {
    padding: 0.75rem 0.9rem;
    border-radius: 12px;
    font-size: 0.9rem;
  }

  .alert.error {
    background: rgba(248, 113, 113, 0.15);
    border: 1px solid rgba(248, 113, 113, 0.35);
    color: rgba(254, 226, 226, 0.92);
  }

  .alert.success {
    background: rgba(34, 197, 94, 0.18);
    border: 1px solid rgba(74, 222, 128, 0.35);
    color: rgba(187, 247, 208, 0.92);
  }

  .cta {
    display: grid;
    gap: 0.6rem;
  }

  .cta p {
    margin: 0;
    color: rgba(226, 232, 240, 0.85);
  }

  .support-note a {
    color: rgba(165, 243, 252, 0.9);
    text-decoration: none;
  }

  .support-note a:hover,
  .support-note a:focus-visible {
    text-decoration: underline;
  }

  @media (max-width: 640px) {
    .upgrade-drawer {
      bottom: 1rem;
      padding: 1.2rem 1.3rem;
    }

    .input-row {
      flex-direction: column;
    }

    button:not(.close-button) {
      width: 100%;
    }
  }
</style>
