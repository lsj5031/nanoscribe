<script lang="ts">
  import {
    getSegments,
    getCurrentSegmentIndex,
    hasSegments,
    getLoading,
    seekToSegment,
    getHoveredSegmentIndex,
    setHoveredSegmentIndex,
    getTranscriptSearchOpen,
    setTranscriptSearchOpen
  } from '$lib/stores/editor.svelte';
  import SegmentItem from './SegmentItem.svelte';

  let scrollContainer: HTMLDivElement | undefined = $state();

  const segments = $derived(getSegments());
  const currentSegmentIndex = $derived(getCurrentSegmentIndex());
  const hasContent = $derived(hasSegments());
  const loading = $derived(getLoading());
  const searchOpen = $derived(getTranscriptSearchOpen());
  const hoveredIndex = $derived(getHoveredSegmentIndex());

  // Search state
  let searchQuery = $state('');
  let currentMatchIdx = $state(-1);

  // Compute match info
  const normalizedQuery = $derived(searchQuery.toLowerCase().trim());

  const matches = $derived.by(() => {
    if (!normalizedQuery) return [];
    const result: { segIndex: number; positions: number[] }[] = [];
    segments.forEach((seg, i) => {
      const text = seg.text.toLowerCase();
      const positions: number[] = [];
      let pos = 0;
      while (pos < text.length) {
        const idx = text.indexOf(normalizedQuery, pos);
        if (idx === -1) break;
        positions.push(idx);
        pos = idx + 1;
      }
      if (positions.length > 0) {
        result.push({ segIndex: i, positions });
      }
    });
    return result;
  });

  const totalMatches = $derived(matches.reduce((sum, m) => sum + m.positions.length, 0));

  // Reset match index when query changes
  $effect(() => {
    normalizedQuery;
    currentMatchIdx = totalMatches > 0 ? 0 : -1;
  });

  // Find which segment index the current match is in
  const currentMatchSegIndex = $derived.by(() => {
    if (currentMatchIdx < 0 || matches.length === 0) return -1;
    let count = 0;
    for (const m of matches) {
      if (currentMatchIdx < count + m.positions.length) return m.segIndex;
      count += m.positions.length;
    }
    return -1;
  });

  // Auto-scroll to current search match
  $effect(() => {
    if (currentMatchSegIndex < 0 || !scrollContainer) return;
    const items = scrollContainer.querySelectorAll('[data-segment-index]');
    const target = items[currentMatchSegIndex] as HTMLElement | undefined;
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

  // Seek to a segment and notify the waveform
  let seekCallback: ((ms: number) => void) | null = $state(null);

  export function setSeekCallback(cb: (ms: number) => void) {
    seekCallback = cb;
  }

  function handleSegmentClick(index: number) {
    const ms = seekToSegment(index);
    if (ms !== null && seekCallback) {
      seekCallback(ms);
    }
  }

  function handleSegmentHover(index: number) {
    setHoveredSegmentIndex(index);
  }

  function handleSegmentLeave() {
    setHoveredSegmentIndex(-1);
  }

  // Auto-scroll to current segment (during playback)
  $effect(() => {
    if (searchOpen && normalizedQuery) return; // Let search scrolling take priority
    if (currentSegmentIndex < 0 || !scrollContainer) return;
    const items = scrollContainer.querySelectorAll('[data-segment-index]');
    const target = items[currentSegmentIndex] as HTMLElement | undefined;
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

  function handleSearchInput(e: Event) {
    const target = e.target as HTMLInputElement;
    searchQuery = target.value;
  }

  function handleSearchNext() {
    if (totalMatches > 0) {
      currentMatchIdx = (currentMatchIdx + 1) % totalMatches;
    }
  }

  function handleSearchPrev() {
    if (totalMatches > 0) {
      currentMatchIdx = (currentMatchIdx - 1 + totalMatches) % totalMatches;
    }
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) {
        handleSearchPrev();
      } else {
        handleSearchNext();
      }
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      searchQuery = '';
      setTranscriptSearchOpen(false);
    }
    // Prevent Space from propagating to global play/pause handler
    if (e.key === ' ') {
      e.stopPropagation();
    }
  }

  function closeSearch() {
    searchQuery = '';
    setTranscriptSearchOpen(false);
  }

  // Focus search input when opened
  let searchInput: HTMLInputElement | undefined = $state();
  $effect(() => {
    if (searchOpen && searchInput) {
      searchInput.focus();
    }
  });
</script>

<div class="flex h-full flex-col">
  <!-- Header -->
  <div class="shrink-0 border-b border-border px-4 py-3">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-text-primary">Transcript</h2>
      {#if !searchOpen && hasContent}
        <button
          onclick={() => setTranscriptSearchOpen(true)}
          class="rounded p-1 text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary"
          title="Search in transcript (Cmd+F)"
          aria-label="Search in transcript"
        >
          <svg
            class="h-3.5 w-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
        </button>
      {/if}
    </div>

    <!-- Search bar -->
    {#if searchOpen}
      <div class="mt-2 flex items-center gap-2">
        <div class="relative flex-1">
          <svg
            class="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            bind:this={searchInput}
            type="text"
            value={searchQuery}
            oninput={handleSearchInput}
            onkeydown={handleSearchKeydown}
            placeholder="Search in transcript…"
            class="w-full rounded border border-border bg-surface-700 py-1.5 pl-7 pr-2 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent"
          />
        </div>
        {#if normalizedQuery}
          <span class="shrink-0 text-xs tabular-nums text-text-muted">
            {currentMatchIdx + 1}/{totalMatches}
          </span>
          <button
            onclick={handleSearchPrev}
            class="rounded p-1 text-text-muted hover:bg-surface-700 hover:text-text-primary"
            aria-label="Previous match"
          >
            <svg
              class="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="18 15 12 9 6 15" />
            </svg>
          </button>
          <button
            onclick={handleSearchNext}
            class="rounded p-1 text-text-muted hover:bg-surface-700 hover:text-text-primary"
            aria-label="Next match"
          >
            <svg
              class="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        {/if}
        <button
          onclick={closeSearch}
          class="rounded p-1 text-text-muted hover:bg-surface-700 hover:text-text-primary"
          aria-label="Close search"
        >
          <svg
            class="h-3.5 w-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    {/if}
  </div>

  <!-- Segment list -->
  <div
    class="flex-1 overflow-y-auto"
    bind:this={scrollContainer}
    role="listbox"
    aria-label="Transcript segments"
  >
    {#if loading}
      <div class="flex items-center justify-center py-12">
        <div class="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent"></div>
      </div>
    {:else if !hasContent}
      <div class="flex flex-col items-center justify-center gap-3 px-4 py-12 text-center">
        <svg
          class="h-10 w-10 text-text-muted"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14,2 14,8 20,8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
        <p class="text-sm text-text-secondary">No transcript yet</p>
        <p class="text-xs text-text-muted">
          Segments will appear here after transcription completes.
        </p>
      </div>
    {:else}
      {#each segments as segment, i (segment.id)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          data-segment-index={i}
          role="option"
          onmouseenter={() => handleSegmentHover(i)}
          onmouseleave={handleSegmentLeave}
        >
          <SegmentItem
            {segment}
            isCurrent={i === currentSegmentIndex}
            isHovered={i === hoveredIndex}
            searchQuery={normalizedQuery}
            onclick={() => handleSegmentClick(i)}
          />
        </div>
      {/each}
    {/if}
  </div>
</div>
