<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { fetchSession, logout } from '$lib/api';
  import { setSession, sessionStore } from '$lib/session';
  import type { SessionInfo } from '$lib/types';

  let { data, children } = $props<{ data: { session: SessionInfo } }>();

  let session = $state(data.session);
  let lastSyncedSession = data.session;
  const currentYear = new Date().getFullYear();

  const unsubscribe = sessionStore.subscribe((value) => {
    session = value;
  });

  onMount(() => {
    setSession(data.session);
  });

  onDestroy(() => {
    unsubscribe();
  });

  $effect(() => {
    if (data.session !== lastSyncedSession) {
      lastSyncedSession = data.session;
      setSession(data.session);
    }
  });

  const handleLogout = async () => {
    await logout();
    const refreshed = await fetchSession();
    session = refreshed;
    setSession(refreshed);
  };
</script>

<div class="app-shell">
  <header class="site-header">
    <a class="brand" href="/">HostScore</a>
    {#if session.authenticated}
      <div class="session-info">
        <span class="user-email">{session.email}</span>
        <span class="credits">{session.credits?.available ?? 0} credit{(session.credits?.available ?? 0) === 1 ? '' : 's'}</span>
        <button type="button" class="logout" onclick={handleLogout}>Log out</button>
      </div>
    {/if}
  </header>
  <main class="site-main">
    {@render children()}
  </main>
  <footer class="site-footer">
    <small>© {currentYear} HostScore - Made in Austin, TX</small>
  </footer>
</div>

<style>
  :global(html),
  :global(body) {
    font-family: 'Zalando Sans', system-ui, sans-serif;
    font-feature-settings: 'kern';
    -webkit-font-smoothing: antialiased;
    margin: 0;
  }

  :global(h1),
  :global(h2),
  :global(h3),
  :global(h4),
  :global(h5),
  :global(h6) {
    font-family: 'Zalando Sans Expanded', 'Zalando Sans', system-ui, sans-serif;
  }

  .app-shell {
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr auto;
    background: #0f172a;
    color: #f8fafc;
  }

  .site-header,
  .site-footer {
    padding: 1rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(148, 163, 184, 0.3);
  }

  .site-footer {
    border-bottom: none;
    border-top: 1px solid rgba(148, 163, 184, 0.3);
    justify-content: center;
  }

  .brand {
    font-weight: 600;
    letter-spacing: 0.04em;
    color: inherit;
    text-decoration: none;
    font-size: 1.05rem;
  }

  .session-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.9rem;
  }

  .user-email {
    font-weight: 500;
    color: rgba(226, 232, 240, 0.95);
  }

  .credits {
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    background: rgba(125, 211, 252, 0.18);
    color: rgba(191, 219, 254, 0.92);
    border: 1px solid rgba(125, 211, 252, 0.35);
    font-weight: 500;
  }

  .logout {
    border: none;
    background: transparent;
    color: rgba(203, 213, 225, 0.75);
    font-size: 0.85rem;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 4px;
  }

  .site-main {
    padding: 2rem 1.5rem 3rem;
    max-width: 1100px;
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }

  @media (max-width: 640px) {
    .site-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .session-info {
      flex-wrap: wrap;
      gap: 0.4rem;
    }

    .site-main {
      padding: 1.5rem 1rem 2.5rem;
    }
  }
</style>
