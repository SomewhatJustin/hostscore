<script lang="ts">
  import { page } from '$app/state';

  let { children } = $props();

  const links = [{ href: '/', label: 'Assess' }];
  const currentYear = new Date().getFullYear();
</script>

<div class="app-shell">
  <header class="site-header">
    <a class="brand" href="/">HostScore</a>
    <nav aria-label="Primary">
      {#each links as link (link.href)}
        {#if link.external}
          <a class:active={page.url.pathname === link.href} href={link.href} rel="noreferrer" target="_blank">
            {link.label}
          </a>
        {:else}
          <a class:active={page.url.pathname === link.href} href={link.href}>
            {link.label}
          </a>
        {/if}
      {/each}
    </nav>
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

  nav a {
    color: #cbd5f5;
    margin-left: 1rem;
    text-decoration: none;
    font-size: 0.95rem;
    padding: 0.4rem 0.7rem;
    border-radius: 999px;
    transition: background-color 0.15s ease, color 0.15s ease;
  }

  nav a:hover,
  nav a:focus-visible {
    background-color: rgba(148, 163, 184, 0.18);
    color: #fff;
  }

  nav a.active {
    background-color: rgba(59, 130, 246, 0.28);
    color: #fff;
  }

  .site-main {
    padding: 2rem 1.5rem 3rem;
  }

  @media (max-width: 640px) {
    .site-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    nav a {
      margin-left: 0;
      margin-right: 0.6rem;
    }

    .site-main {
      padding: 1.5rem 1rem 2.5rem;
    }
  }
</style>
