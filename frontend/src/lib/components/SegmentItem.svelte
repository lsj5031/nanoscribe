<script lang="ts">
  import type { Segment } from '$lib/stores/editor.svelte';
  import { formatTime, getSpeakerColor } from '$lib/stores/editor.svelte';

  let {
    segment,
    isCurrent = false,
    onclick
  }: {
    segment: Segment;
    isCurrent: boolean;
    onclick: () => void;
  } = $props();

  const timeDisplay = $derived(formatTime(segment.start_ms));
  const speakerColor = $derived(getSpeakerColor(segment.speaker_key));
</script>

<button
  class="w-full cursor-pointer border-l-2 px-4 py-2.5 text-left transition-colors {isCurrent
    ? 'border-accent bg-accent/5'
    : 'border-transparent hover:bg-surface-700'}"
  role="option"
  aria-selected={isCurrent}
  {onclick}
>
  <div class="flex items-start gap-3">
    <!-- Timestamp -->
    <span
      class="shrink-0 font-mono text-xs tabular-nums {isCurrent
        ? 'text-accent'
        : 'text-text-muted'}"
    >
      {timeDisplay}
    </span>

    <div class="min-w-0 flex-1">
      <!-- Speaker badge -->
      {#if segment.speaker_key}
        <div class="mb-1 flex items-center gap-1.5">
          <span class="inline-block h-2 w-2 rounded-full" style="background-color: {speakerColor}"
          ></span>
          <span class="text-xs font-medium text-text-secondary">{segment.speaker_key}</span>
        </div>
      {/if}

      <!-- Text -->
      <p class="text-sm leading-relaxed {isCurrent ? 'text-text-primary' : 'text-text-secondary'}">
        {segment.text || '...'}
      </p>
    </div>
  </div>
</button>
