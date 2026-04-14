<script lang="ts">
  import {
    getSegments,
    getCurrentSegmentIndex,
    hasSegments,
    getLoading,
    seekToSegment
  } from '$lib/stores/editor.svelte';
  import SegmentItem from './SegmentItem.svelte';

  let scrollContainer: HTMLDivElement | undefined = $state();

  const segments = $derived(getSegments());
  const currentSegmentIndex = $derived(getCurrentSegmentIndex());
  const hasContent = $derived(hasSegments());
  const loading = $derived(getLoading());

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

  // Auto-scroll to current segment
  $effect(() => {
    if (currentSegmentIndex < 0 || !scrollContainer) return;
    const items = scrollContainer.querySelectorAll('[data-segment-index]');
    const target = items[currentSegmentIndex] as HTMLElement | undefined;
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
</script>

<div class="flex h-full flex-col">
  <!-- Header -->
  <div class="shrink-0 border-b border-border px-4 py-3">
    <h2 class="text-sm font-semibold text-text-primary">Transcript</h2>
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
        <div data-segment-index={i}>
          <SegmentItem
            {segment}
            isCurrent={i === currentSegmentIndex}
            onclick={() => handleSegmentClick(i)}
          />
        </div>
      {/each}
    {/if}
  </div>
</div>
