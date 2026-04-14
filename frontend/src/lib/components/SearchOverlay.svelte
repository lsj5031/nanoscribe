<!--
  SearchOverlay: Full-screen modal search with keyboard navigation.
  Activated globally by Cmd/Ctrl+K or via the TopBar search button.
-->
<script lang="ts">
  import {
    getQuery,
    getResults,
    getTotal,
    getLoading,
    getOpen,
    setQuery,
    closeSearch,
    selectResult,
    formatTimestamp,
    type SearchResult
  } from '$lib/stores/search.svelte';

  let inputEl: HTMLInputElement | undefined = $state();
  let activeIndex = $state(-1);

  const isOpen = $derived(getOpen());
  const query = $derived(getQuery());
  const results = $derived(getResults());
  const total = $derived(getTotal());
  const loading = $derived(getLoading());

  // Reset active index when results change
  $effect(() => {
    results;
    activeIndex = -1;
  });

  // Auto-focus input when overlay opens
  $effect(() => {
    if (isOpen) {
      // Reset input value to current query
      activeIndex = -1;
      setTimeout(() => inputEl?.focus(), 0);
    }
  });

  function handleInput(e: Event) {
    const target = e.target as HTMLInputElement;
    setQuery(target.value);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeSearch();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, results.length - 1);
      scrollToActive();
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = activeIndex <= 0 ? -1 : activeIndex - 1;
      scrollToActive();
      return;
    }

    if (e.key === 'Enter' && activeIndex >= 0 && activeIndex < results.length) {
      e.preventDefault();
      selectResult(results[activeIndex]);
      return;
    }
  }

  function scrollToActive() {
    // Use requestAnimationFrame so DOM updates first
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-search-index="${activeIndex}"]`);
      el?.scrollIntoView({ block: 'nearest' });
    });
  }

  function handleBackdropClick() {
    closeSearch();
  }

  function handlePanelClick(e: MouseEvent) {
    e.stopPropagation();
  }

  function handleResultClick(result: SearchResult) {
    selectResult(result);
  }

  function handleResultMouseEnter(index: number) {
    activeIndex = index;
  }

  function truncate(text: string, maxLen: number): string {
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '…';
  }
</script>

{#if isOpen}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-start justify-center bg-surface-900/70 pt-[15vh] backdrop-blur-sm transition-opacity"
    onclick={handleBackdropClick}
    onkeydown={handleKeydown}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
      class="flex w-full max-w-xl flex-col overflow-hidden rounded-xl border border-border bg-surface-800 shadow-2xl"
      onclick={handlePanelClick}
    >
      <!-- Search input -->
      <div class="flex items-center gap-3 border-b border-border px-4 py-3">
        {#if loading}
          <div
            class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-accent"
          ></div>
        {:else}
          <svg
            class="h-4 w-4 shrink-0 text-text-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
        {/if}
        <input
          bind:this={inputEl}
          type="text"
          value={query}
          oninput={handleInput}
          placeholder="Search memos…"
          class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none"
          aria-label="Search memos"
          aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined}
          role="combobox"
          aria-expanded="true"
          aria-controls="search-results"
        />
        <kbd class="rounded bg-surface-700 px-1.5 py-0.5 text-xs text-text-muted">Esc</kbd>
      </div>

      <!-- Results area -->
      <div id="search-results" class="max-h-80 overflow-y-auto" role="listbox">
        {#if !query.trim()}
          <div class="px-4 py-8 text-center text-sm text-text-muted">Start typing to search…</div>
        {:else if loading}
          <div class="px-4 py-8 text-center text-sm text-text-muted">Searching…</div>
        {:else if total === 0}
          <div class="px-4 py-8 text-center text-sm text-text-muted">
            No results found for "{query}"
          </div>
        {:else}
          {#each results as result, i (i)}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_interactive_supports_focus -->
            <div
              id="search-result-{i}"
              data-search-index={i}
              role="option"
              tabindex="-1"
              aria-selected={i === activeIndex}
              class="flex cursor-pointer items-start gap-3 border-b border-border/50 px-4 py-3 last:border-b-0 {i ===
              activeIndex
                ? 'bg-surface-600'
                : 'bg-surface-800 hover:bg-surface-700'}"
              onclick={() => handleResultClick(result)}
              onmouseenter={() => handleResultMouseEnter(i)}
            >
              <!-- Icon -->
              <div class="mt-0.5 shrink-0">
                {#if result.match_type === 'title'}
                  <svg
                    class="h-4 w-4 text-accent"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14,2 14,8 20,8" />
                  </svg>
                {:else}
                  <svg
                    class="h-4 w-4 text-text-muted"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                    <line x1="12" y1="19" x2="12" y2="23" />
                  </svg>
                {/if}
              </div>

              <!-- Content -->
              <div class="min-w-0 flex-1">
                {#if result.match_type === 'title'}
                  <p class="text-sm font-medium text-text-primary">{result.memo_title}</p>
                  <span
                    class="mt-1 inline-block rounded bg-accent/20 px-1.5 py-0.5 text-xs text-accent"
                  >
                    Title match
                  </span>
                {:else}
                  <p class="text-sm text-text-primary">
                    {result.segment_text ? truncate(result.segment_text, 150) : ''}
                  </p>
                  <div class="mt-1 flex items-center gap-2">
                    {#if result.start_ms != null}
                      <span class="rounded bg-surface-700 px-1.5 py-0.5 text-xs text-accent">
                        {formatTimestamp(result.start_ms)}
                      </span>
                    {/if}
                    <span class="text-xs text-text-muted">{result.memo_title}</span>
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        {/if}
      </div>

      <!-- Footer hint -->
      {#if total > 0}
        <div
          class="flex items-center gap-4 border-t border-border px-4 py-2 text-xs text-text-muted"
        >
          <span class="flex items-center gap-1">
            <kbd class="rounded bg-surface-700 px-1 py-0.5">↑↓</kbd> navigate
          </span>
          <span class="flex items-center gap-1">
            <kbd class="rounded bg-surface-700 px-1 py-0.5">↵</kbd> select
          </span>
          <span class="flex items-center gap-1">
            <kbd class="rounded bg-surface-700 px-1 py-0.5">esc</kbd> close
          </span>
          <span class="ml-auto">{total} result{total !== 1 ? 's' : ''}</span>
        </div>
      {/if}
    </div>
  </div>
{/if}
