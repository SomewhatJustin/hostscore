<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  interface SubmitDetail {
    url: string;
    force: boolean;
  }

  const dispatch = createEventDispatcher<{ submit: SubmitDetail }>();

  let { initialUrl = '', loading = false } = $props<{ initialUrl?: string; loading?: boolean }>();

  let url = $state(initialUrl);
  let force = $state(false);

  const trimmedUrl = $derived(url.trim());
  const disableSubmit = $derived(!trimmedUrl || loading);

  const handleSubmit = (event: SubmitEvent) => {
    event.preventDefault();
    if (disableSubmit) return;
    dispatch('submit', { url: trimmedUrl, force });
  };
</script>

<form class="assessment-form" onsubmit={handleSubmit}>
  <div class="fields">
    <label for="listing-url">
      Airbnb listing URL
      <span class="hint">Example: https://www.airbnb.com/rooms/12345678</span>
    </label>
    <div class="input-row">
      <input
        id="listing-url"
        name="listing-url"
        type="url"
        placeholder="https://www.airbnb.com/rooms/... "
        bind:value={url}
        aria-describedby="force-check"
        required
        pattern="https?://.+"
        autocomplete="off"
      />
      <button type="submit" disabled={disableSubmit}>
        {#if loading}
          <span class="spinner" aria-hidden="true"></span>
          Assessing…
        {:else}
          Assess listing
        {/if}
      </button>
    </div>
  </div>

  <label class="force-refresh" for="force-check">
    <input id="force-check" type="checkbox" bind:checked={force} disabled={loading} />
    Force fresh render (skip cached assessment)
  </label>
</form>

<style>
  .assessment-form {
    display: grid;
    gap: 1rem;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 22px 45px -25px rgba(15, 23, 42, 0.7);
  }

  .fields {
    display: grid;
    gap: 0.6rem;
  }

  label {
    font-weight: 500;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .hint {
    font-size: 0.85rem;
    color: rgba(203, 213, 225, 0.85);
    font-weight: 400;
  }

  .input-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  input[type='url'] {
    flex: 1;
    min-width: 0;
    padding: 0.85rem 1rem;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.45);
    background: rgba(15, 23, 42, 0.95);
    color: #f8fafc;
    font-size: 1rem;
    transition: border 0.15s ease, box-shadow 0.15s ease;
  }

  input[type='url']:focus-visible {
    outline: none;
    border-color: rgba(96, 165, 250, 0.7);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35);
  }

  button[type='submit'] {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    padding: 0.85rem 1.4rem;
    border-radius: 12px;
    border: none;
    font-weight: 600;
    font-size: 0.98rem;
    letter-spacing: 0.015em;
    cursor: pointer;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: #fff;
    box-shadow: 0 10px 30px -18px rgba(29, 78, 216, 0.9);
    transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
  }

  button[type='submit']:hover:enabled,
  button[type='submit']:focus-visible:enabled {
    transform: translateY(-1px);
    box-shadow: 0 16px 40px -18px rgba(29, 78, 216, 0.9);
  }

  button[disabled] {
    opacity: 0.6;
    cursor: not-allowed;
    box-shadow: none;
  }

  .force-refresh {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    font-size: 0.95rem;
    color: #cbd5f5;
  }

  .force-refresh input {
    accent-color: #38bdf8;
    width: 1.1rem;
    height: 1.1rem;
  }

  .spinner {
    width: 1rem;
    height: 1rem;
    border-radius: 999px;
    border: 2px solid rgba(255, 255, 255, 0.55);
    border-top-color: rgba(15, 23, 42, 0.9);
    animation: spin 0.75s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 640px) {
    .assessment-form {
      padding: 1.25rem;
    }

    .input-row {
      flex-direction: column;
      align-items: stretch;
    }

    button[type='submit'] {
      width: 100%;
      padding: 0.85rem 1rem;
    }
  }
</style>
