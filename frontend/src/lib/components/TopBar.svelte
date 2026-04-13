<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  let searchQuery = $state('');
  let searchOpen = $state(false);
  let searchInput: HTMLInputElement | undefined = $state();

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      searchOpen = false;
      searchQuery = '';
    } else if (e.key === 'Enter' && searchQuery.trim()) {
      // Navigate to home with search query (search will be implemented in M4)
      goto(`/?q=${encodeURIComponent(searchQuery.trim())}`);
      searchOpen = false;
    }
  }

  function openSearch() {
    searchOpen = true;
    setTimeout(() => searchInput?.focus(), 0);
  }

  function navigateToSettings() {
    goto('/settings');
  }

  function navigateToHome() {
    goto('/');
  }
</script>

<header
  class="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface-800 px-4"
>
  <!-- Logo / Home link -->
  <button
    onclick={navigateToHome}
    class="flex items-center gap-2 text-text-primary transition-colors hover:text-accent"
    aria-label="Go to home"
  >
    <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
    <span class="text-lg font-semibold">
      Nano<span class="text-accent">Scribe</span>
    </span>
  </button>

  <!-- Search -->
  <div class="flex items-center gap-2">
    {#if searchOpen}
      <div class="relative">
        <input
          bind:this={searchInput}
          bind:value={searchQuery}
          onkeydown={handleSearchKeydown}
          type="text"
          placeholder="Search memos…"
          class="w-64 rounded-lg border border-border bg-surface-700 px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent"
          aria-label="Search memos"
        />
        <kbd
          class="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-surface-600 px-1.5 py-0.5 text-xs text-text-muted"
        >
          Esc
        </kbd>
      </div>
    {:else}
      <button
        onclick={openSearch}
        class="flex items-center gap-2 rounded-lg border border-border bg-surface-700 px-3 py-1.5 text-sm text-text-muted transition-colors hover:border-accent hover:text-text-secondary"
        aria-label="Open search"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <span>Search…</span>
        <kbd class="rounded bg-surface-600 px-1.5 py-0.5 text-xs">⌘K</kbd>
      </button>
    {/if}

    <!-- Settings -->
    <button
      onclick={navigateToSettings}
      class="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary"
      aria-label="Settings"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path
          d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        />
        <circle cx="12" cy="12" r="3" />
      </svg>
    </button>
  </div>
</header>
