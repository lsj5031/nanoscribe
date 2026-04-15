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

  let searchQuery = $state('');
  let currentMatchIdx = $state(-1);

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

  $effect(() => {
    normalizedQuery;
    currentMatchIdx = totalMatches > 0 ? 0 : -1;
  });

  const currentMatchSegIndex = $derived.by(() => {
    if (currentMatchIdx < 0 || matches.length === 0) return -1;
    let count = 0;
    for (const m of matches) {
      if (currentMatchIdx < count + m.positions.length) return m.segIndex;
      count += m.positions.length;
    }
    return -1;
  });

  $effect(() => {
    if (currentMatchSegIndex < 0 || !scrollContainer) return;
    const items = scrollContainer.querySelectorAll('[data-segment-index]');
    const target = items[currentMatchSegIndex] as HTMLElement | undefined;
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

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

  $effect(() => {
    if (searchOpen && normalizedQuery) return;
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
    if (e.key === ' ') {
      e.stopPropagation();
    }
  }

  function closeSearch() {
    searchQuery = '';
    setTranscriptSearchOpen(false);
  }

  let searchInput: HTMLInputElement | undefined = $state();
  $effect(() => {
    if (searchOpen && searchInput) {
      searchInput.focus();
    }
  });
</script>

<div class="flex h-full flex-col bg-[#F9F8F6]">
  <!-- Header -->
  <div class="shrink-0 border-b border-[#1A1A1A]/20 px-12 py-8 shadow-[0_2px_8px_rgba(0,0,0,0.02)]">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-serif text-[#1A1A1A]">Transcript</h2>
      {#if !searchOpen && hasContent}
        <button
          onclick={() => setTranscriptSearchOpen(true)}
          class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
          title="Search in transcript (Cmd+F)"
          aria-label="Search in transcript"
        >
          Search
        </button>
      {/if}
    </div>

    <!-- Search bar -->
    {#if searchOpen}
      <div class="mt-8 flex items-center gap-6">
        <div class="relative flex-1">
          <input
            bind:this={searchInput}
            type="text"
            value={searchQuery}
            oninput={handleSearchInput}
            onkeydown={handleSearchKeydown}
            placeholder="SEARCH IN TRANSCRIPT…"
            class="w-full border-b border-[#1A1A1A]/20 bg-transparent py-2 pl-2 pr-2 text-xs uppercase tracking-[0.2em] text-[#1A1A1A] placeholder-[#1A1A1A]/40 outline-none transition-colors duration-500 ease-luxury focus:border-[#D4AF37] rounded-none"
          />
        </div>
        {#if normalizedQuery}
          <span class="shrink-0 font-sans text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60">
            {currentMatchIdx + 1} / {totalMatches}
          </span>
          <div class="flex gap-4">
            <button
              onclick={handleSearchPrev}
              class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
              aria-label="Previous match"
            >
              Prev
            </button>
            <button
              onclick={handleSearchNext}
              class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
              aria-label="Next match"
            >
              Next
            </button>
          </div>
        {/if}
        <button
          onclick={closeSearch}
          class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
          aria-label="Close search"
        >
          Close
        </button>
      </div>
    {/if}
  </div>

  <!-- Segment list -->
  <div
    class="flex-1 overflow-y-auto p-0"
    bind:this={scrollContainer}
    role="listbox"
    aria-label="Transcript segments"
  >
    {#if loading}
      <div class="flex items-center justify-center py-24">
        <div class="h-10 w-10 animate-spin border-t border-l border-[#1A1A1A]"></div>
      </div>
    {:else if !hasContent}
      <div class="flex flex-col items-center justify-center gap-8 px-12 py-24 text-center">
        <div class="border border-[#1A1A1A]/20 p-8 shadow-[0_2px_8px_rgba(0,0,0,0.02)]">
          <svg
            class="h-8 w-8 text-[#1A1A1A]/40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        </div>
        <p class="text-sm font-sans text-[#1A1A1A]">No transcript yet</p>
        <p class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60">
          Segments will appear here after transcription.
        </p>
      </div>
    {:else}
      {#each segments as segment, i (segment.id)}
        <div
          data-segment-index={i}
          role="presentation"
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
