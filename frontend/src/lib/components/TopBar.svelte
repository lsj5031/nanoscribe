<script lang="ts">
  import { goto } from '$app/navigation';
  import { openSearch } from '$lib/stores/search.svelte';

  function navigateToSettings() {
    goto('/settings');
  }

  function navigateToHome() {
    goto('/');
  }
</script>

<header
  class="flex h-20 shrink-0 items-center justify-between border-b border-border bg-transparent px-8 md:px-16"
>
  <!-- Logo / Home link -->
  <button
    onclick={navigateToHome}
    class="group flex items-center gap-4 text-text-primary transition-colors hover:text-accent duration-700 ease-luxury"
    aria-label="Go to home"
  >
    <img
      src="/icon-192.png"
      alt="NanoScribe logo"
      width="32"
      height="32"
      class="h-8 w-8 transition-transform duration-700 group-hover:scale-105"
    />
    <span class="text-2xl font-serif tracking-tight">
      Nano<span class="italic">Scribe</span>
    </span>
  </button>

  <!-- Right side: search + settings -->
  <div class="flex items-center gap-6">
    <button
      onclick={openSearch}
      class="group flex h-10 items-center gap-3 border-b border-border bg-transparent px-0 py-2 text-sm text-text-muted transition-colors duration-500 hover:border-accent hover:text-text-primary ease-luxury"
      aria-label="Open search"
    >
      <svg class="h-4 w-4 stroke-[1.5px]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
      <span class="font-serif italic text-[#6C6863]">Search…</span>
      <kbd class="text-[10px] tracking-[0.2em] uppercase text-text-primary ml-4">⌘K</kbd>
    </button>

    <!-- Settings -->
    <button
      onclick={navigateToSettings}
      class="flex items-center justify-center h-10 w-10 text-text-primary transition-colors duration-500 hover:text-accent ease-luxury"
      aria-label="Settings"
    >
      <svg class="h-5 w-5 stroke-1" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path
          d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        />
        <circle cx="12" cy="12" r="3" />
      </svg>
    </button>
  </div>
</header>
