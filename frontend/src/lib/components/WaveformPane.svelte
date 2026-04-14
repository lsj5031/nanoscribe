<script lang="ts">
  import WaveSurfer from 'wavesurfer.js';
  import {
    getMemoId,
    getIsPlaying,
    getPlaybackSpeed,
    getSegments,
    getCurrentTimeMs,
    getDurationMs,
    setIsPlaying,
    setCurrentTimeMs,
    setDurationMs,
    setPlaybackSpeed,
    formatTime,
    getSpeakerColor,
    getSpeeds
  } from '$lib/stores/editor.svelte';

  let { containerHeight = $bindable() }: { containerHeight?: number } = $props();

  let waveformContainer: HTMLDivElement | undefined = $state();
  let ws: WaveSurfer | null = $state(null);
  let segmentBandCanvas: HTMLCanvasElement | undefined = $state();

  const memoId = $derived(getMemoId());
  const isPlaying = $derived(getIsPlaying());
  const playbackSpeed = $derived(getPlaybackSpeed());
  const segments = $derived(getSegments());
  const currentTimeMs = $derived(getCurrentTimeMs());
  const durationMs = $derived(getDurationMs());
  const speeds = $derived(getSpeeds());

  const currentTimeDisplay = $derived(formatTime(currentTimeMs));
  const durationDisplay = $derived(formatTime(durationMs));

  // Initialize wavesurfer
  $effect(() => {
    if (!waveformContainer || !memoId) return;

    const instance = WaveSurfer.create({
      container: waveformContainer,
      waveColor: '#3a3d4e',
      progressColor: '#00d4ff',
      cursorColor: '#00d4ff',
      cursorWidth: 2,
      height: 128,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      backend: 'WebAudio'
    });

    instance.load(`/api/memos/${memoId}/audio`);

    instance.on('ready', () => {
      setDurationMs(instance.getDuration() * 1000);
      drawSegmentBand();
    });

    instance.on('audioprocess', () => {
      setCurrentTimeMs(instance.getCurrentTime() * 1000);
    });

    instance.on('seeking', () => {
      setCurrentTimeMs(instance.getCurrentTime() * 1000);
    });

    instance.on('play', () => setIsPlaying(true));
    instance.on('pause', () => setIsPlaying(false));

    ws = instance;

    return () => {
      instance.destroy();
      ws = null;
    };
  });

  // Sync playback speed
  $effect(() => {
    if (ws) {
      ws.setPlaybackRate(playbackSpeed);
    }
  });

  // Redraw segment band when segments change
  $effect(() => {
    segments;
    drawSegmentBand();
  });

  function drawSegmentBand() {
    if (!segmentBandCanvas || !durationMs || durationMs <= 0 || segments.length === 0) return;

    const ctx = segmentBandCanvas.getContext('2d');
    if (!ctx) return;

    const rect = segmentBandCanvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    segmentBandCanvas.width = rect.width * dpr;
    segmentBandCanvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, rect.width, rect.height);

    for (const seg of segments) {
      const startX = (seg.start_ms / durationMs) * rect.width;
      const endX = (seg.end_ms / durationMs) * rect.width;
      const color = getSpeakerColor(seg.speaker_key);

      ctx.fillStyle = color;
      ctx.globalAlpha = 0.6;
      if (ctx.roundRect) {
        ctx.beginPath();
        ctx.roundRect(startX, 2, Math.max(endX - startX, 2), rect.height - 4, 3);
        ctx.fill();
      } else {
        ctx.fillRect(startX, 2, Math.max(endX - startX, 2), rect.height - 4);
      }
    }
    ctx.globalAlpha = 1;
  }

  function togglePlay() {
    ws?.playPause();
  }

  function handleSpeedChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    setPlaybackSpeed(parseFloat(target.value) as 0.5 | 0.75 | 1 | 1.25 | 1.5 | 2);
  }

  export function seekToTime(ms: number) {
    if (ws) {
      ws.seekTo(ms / (durationMs || 1) / 1000);
      setCurrentTimeMs(ms);
    }
  }
</script>

<div class="flex h-full flex-col">
  <!-- Waveform -->
  <div class="flex-1 px-4 pt-4">
    <div bind:this={waveformContainer} class="h-full min-h-[128px]"></div>
  </div>

  <!-- Speaker segment band -->
  <div class="px-4 py-1">
    <canvas bind:this={segmentBandCanvas} class="h-4 w-full rounded"></canvas>
  </div>

  <!-- Transport bar -->
  <div class="flex items-center gap-3 border-t border-border bg-surface-800 px-4 py-2">
    <!-- Play/Pause -->
    <button
      onclick={togglePlay}
      data-play-button
      class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-surface-900 transition-colors hover:bg-accent-hover"
      aria-label={isPlaying ? 'Pause' : 'Play'}
    >
      {#if isPlaying}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16" rx="1" />
          <rect x="14" y="4" width="4" height="16" rx="1" />
        </svg>
      {:else}
        <svg class="h-5 w-5 ml-0.5" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="6,3 20,12 6,21" />
        </svg>
      {/if}
    </button>

    <!-- Time display -->
    <span class="shrink-0 font-mono text-sm text-text-secondary tabular-nums">
      {currentTimeDisplay} / {durationDisplay}
    </span>

    <!-- Speed selector -->
    <div class="ml-auto flex items-center gap-1">
      <label for="speed-select" class="text-xs text-text-muted">Speed:</label>
      <select
        id="speed-select"
        value={playbackSpeed}
        onchange={handleSpeedChange}
        class="rounded border border-border bg-surface-700 px-2 py-1 text-xs text-text-primary outline-none focus:border-accent"
      >
        {#each speeds as speed}
          <option value={speed}>{speed}x</option>
        {/each}
      </select>
    </div>
  </div>
</div>
