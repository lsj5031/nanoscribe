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
    getSpeeds,
    getZoomLevel,
    setZoomLevel,
    getHoveredSegmentIndex,
    setHoveredSegmentIndex
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
  const zoomLevel = $derived(getZoomLevel());
  const hoveredIndex = $derived(getHoveredSegmentIndex());

  const currentTimeDisplay = $derived(formatTime(currentTimeMs));
  const durationDisplay = $derived(formatTime(durationMs));

  $effect(() => {
    if (!waveformContainer || !memoId) return;

    const instance = WaveSurfer.create({
      container: waveformContainer,
      waveColor: '#1A1A1A40', // Charcoal with 25% opacity
      progressColor: '#D4AF37', // Gold for active
      cursorColor: '#D4AF37',
      cursorWidth: 1,
      height: 200,
      barWidth: 1,
      barGap: 4,
      barRadius: 0,
      normalize: true,
      backend: 'WebAudio'
    });

    instance.load(`/api/memos/${memoId}/audio`);

    instance.on('ready', () => {
      setDurationMs(instance.getDuration() * 1000);
      drawSegmentBand();
      if (zoomLevel > 1) {
        instance.zoom(zoomLevel * 100);
      }
    });

    instance.on('audioprocess', () => {
      setCurrentTimeMs(instance.getCurrentTime() * 1000);
    });

    instance.on('seeking', () => {
      setCurrentTimeMs(instance.getCurrentTime() * 1000);
    });

    instance.on('play', () => setIsPlaying(true));
    instance.on('pause', () => setIsPlaying(false));

    (instance as any).on('hover', (event: { position: number }) => {
      if (!durationMs || durationMs <= 0) return;
      const hoverTimeMs = event.position * 1000;
      const idx = _findSegmentIndex(hoverTimeMs);
      setHoveredSegmentIndex(idx);
    });

    instance.on('interaction', () => {
      setHoveredSegmentIndex(-1);
    });

    ws = instance;

    return () => {
      instance.destroy();
      ws = null;
    };
  });

  $effect(() => {
    if (ws) {
      ws.setPlaybackRate(playbackSpeed);
    }
  });

  $effect(() => {
    segments;
    hoveredIndex;
    drawSegmentBand();
  });

  function _findSegmentIndex(timeMs: number): number {
    for (let i = 0; i < segments.length; i++) {
      if (timeMs >= segments[i].start_ms && timeMs <= segments[i].end_ms) return i;
    }
    for (let i = 0; i < segments.length; i++) {
      if (segments[i].start_ms > timeMs) return i;
    }
    return -1;
  }

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

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      const startX = (seg.start_ms / durationMs) * rect.width;
      const endX = (seg.end_ms / durationMs) * rect.width;
      const color = getSpeakerColor(seg.speaker_key);
      const isHovered = i === hoveredIndex;

      ctx.fillStyle = color;
      ctx.globalAlpha = isHovered ? 1.0 : 0.4;
      ctx.fillRect(startX, 0, Math.max(endX - startX, 1), rect.height);

      if (isHovered) {
        ctx.strokeStyle = '#D4AF37';
        ctx.lineWidth = 1;
        ctx.strokeRect(startX, 0, Math.max(endX - startX, 1), rect.height);
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

  function handleZoomIn() {
    const newLevel = Math.min(8, zoomLevel + 1);
    setZoomLevel(newLevel);
    ws?.zoom(newLevel * 100);
  }

  function handleZoomOut() {
    const newLevel = Math.max(1, zoomLevel - 1);
    setZoomLevel(newLevel);
    if (newLevel === 1) {
      resetZoom();
    } else {
      ws?.zoom(newLevel * 100);
    }
  }

  function resetZoom() {
    setZoomLevel(1);
    if (ws) {
      (ws as any).zoom(false);
    }
  }

  export function seekToTime(ms: number) {
    if (ws) {
      ws.seekTo(ms / (durationMs || 1) / 1000);
      setCurrentTimeMs(ms);
    }
  }
</script>

<div class="flex h-full flex-col bg-[#F9F8F6]">
  <!-- Waveform -->
  <div
    class="flex-1 overflow-x-auto px-12 pt-12 transition-all duration-500 ease-luxury {isPlaying
      ? 'grayscale-0 opacity-100'
      : 'grayscale opacity-70'} hover:grayscale-0 hover:opacity-100"
  >
    <div bind:this={waveformContainer} class="h-full min-h-[200px]"></div>
  </div>

  <!-- Speaker segment band -->
  <div
    class="px-12 py-8 transition-all duration-500 ease-luxury {isPlaying
      ? 'grayscale-0 opacity-100'
      : 'grayscale opacity-70'} hover:grayscale-0 hover:opacity-100"
  >
    <canvas bind:this={segmentBandCanvas} class="h-2 w-full rounded-none"></canvas>
  </div>

  <!-- Transport bar -->
  <div
    class="flex items-center gap-12 border-t border-[#1A1A1A]/20 bg-[#F9F8F6] px-12 py-8 shadow-[0_2px_8px_rgba(0,0,0,0.02)]"
  >
    <!-- Play/Pause -->
    <button
      onclick={togglePlay}
      data-play-button
      class="flex h-16 w-16 shrink-0 items-center justify-center border border-[#1A1A1A]/20 bg-[#F9F8F6] text-[#1A1A1A] transition-all duration-500 ease-luxury hover:border-[#D4AF37] hover:text-[#D4AF37] rounded-none"
      aria-label={isPlaying ? 'Pause' : 'Play'}
    >
      {#if isPlaying}
        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16" />
          <rect x="14" y="4" width="4" height="16" />
        </svg>
      {:else}
        <svg class="h-6 w-6 ml-1" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="5,3 21,12 5,21" />
        </svg>
      {/if}
    </button>

    <!-- Time display -->
    <span class="shrink-0 font-sans text-xs uppercase tracking-[0.2em] text-[#1A1A1A]">
      {currentTimeDisplay} / {durationDisplay}
    </span>

    <!-- Zoom controls -->
    <div class="flex items-center gap-6">
      <button
        onclick={handleZoomOut}
        disabled={zoomLevel <= 1}
        class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] disabled:opacity-30 disabled:pointer-events-none rounded-none"
        aria-label="Zoom out"
        title="Zoom out"
      >
        Zoom Out
      </button>
      <button
        onclick={() => {
          if (zoomLevel > 1) resetZoom();
        }}
        class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A] transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
        aria-label="Reset zoom"
        title="Reset zoom"
      >
        {zoomLevel}X
      </button>
      <button
        onclick={handleZoomIn}
        disabled={zoomLevel >= 8}
        class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] disabled:opacity-30 disabled:pointer-events-none rounded-none"
        aria-label="Zoom in"
        title="Zoom in"
      >
        Zoom In
      </button>
    </div>

    <!-- Speed selector -->
    <div class="ml-auto flex items-center gap-4">
      <label for="speed-select" class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60">
        Speed
      </label>
      <select
        id="speed-select"
        value={playbackSpeed}
        onchange={handleSpeedChange}
        class="border-b border-[#1A1A1A]/20 bg-transparent py-1 pr-4 text-xs uppercase tracking-[0.2em] text-[#1A1A1A] outline-none transition-colors duration-500 ease-luxury focus:border-[#D4AF37] rounded-none cursor-pointer"
      >
        {#each speeds as speed}
          <option value={speed} class="bg-[#F9F8F6] text-[#1A1A1A]">{speed}X</option>
        {/each}
      </select>
    </div>
  </div>
</div>
