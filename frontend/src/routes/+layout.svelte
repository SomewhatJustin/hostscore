<script lang="ts">
  let { children } = $props();

  const currentYear = new Date().getFullYear();
</script>

<div class="app-shell">
  <header class="site-header">
    <a class="brand" href="/">HostScore</a>
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

  .site-main {
    padding: 2rem 1.5rem 3rem;
  }

  @media (max-width: 640px) {
    .site-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .site-main {
      padding: 1.5rem 1rem 2.5rem;
    }
  }
</style>
