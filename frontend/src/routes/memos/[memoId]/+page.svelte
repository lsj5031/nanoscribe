<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import WaveformPane from '$lib/components/WaveformPane.svelte';
  import TranscriptPane from '$lib/components/TranscriptPane.svelte';
  import ExportMenu from '$lib/components/ExportMenu.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';
  import { showSuccess, showError, showWarning } from '$lib/stores/toasts.svelte';
  import {
    initEditor,
    cleanupEditor,
    getMemo,
    getLoading,
    getError,
    getRevision,
    getSegments,
    getLeftPaneWidthPct,
    getIsDraggingDivider,
    setLeftPaneWidthPct,
    setIsDraggingDivider,
    getIsPlaying,
    getCurrentTimeMs,
    getDurationMs,
    getEditingSegmentId,
    getCurrentSegmentIndex,
    setCurrentTimeMs,
    seekToSegment,
    setEditingSegmentId,
    flushSave,
    getFullTranscriptText,
    connectEditorSSE,
    hasSegments
  } from '$lib/stores/editor.svelte';

  let waveformPane: WaveformPane | undefined = $state();
  let transcriptPane: TranscriptPane | undefined = $state();
  let containerEl: HTMLDivElement | undefined = $state();
  let exportMenuOpen = $state(false);
  let copyTooltip = $state('');

  const memoId = $derived($page.params.memoId ?? '');
  const memo = $derived(getMemo());
  const loading = $derived(getLoading());
  const error = $derived(getError());
  const leftPct = $derived(getLeftPaneWidthPct());
  const isDragging = $derived(getIsDraggingDivider());
  const isPlaying = $derived(getIsPlaying());
  const currentTimeMs = $derived(getCurrentTimeMs());
  const durationMs = $derived(getDurationMs());
  const capabilities = $derived(getCapabilities());
  const hasContent = $derived(hasSegments());

  $effect(() => {
    if (memoId) {
      initEditor(memoId);
    }
    return () => {
      cleanupEditor();
    };
  });

  $effect(() => {
    function handleBeforeUnload() {
      flushSave();
    }
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      flushSave();
    };
  });

  $effect(() => {
    if (transcriptPane && waveformPane) {
      transcriptPane.setSeekCallback((ms: number) => {
        waveformPane?.seekToTime(ms);
      });
    }
  });

  function _getCurrentIndex(): number {
    const segs = getSegments();
    const time = getCurrentTimeMs();
    if (segs.length === 0) return -1;
    for (let i = 0; i < segs.length; i++) {
      if (time >= segs[i].start_ms && time <= segs[i].end_ms) return i;
    }
    for (let i = 0; i < segs.length; i++) {
      if (segs[i].start_ms > time) return i;
    }
    return segs.length - 1;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (
      e.target instanceof HTMLInputElement ||
      e.target instanceof HTMLTextAreaElement ||
      e.target instanceof HTMLSelectElement
    ) {
      if (e.key === 'Escape') {
        (e.target as HTMLElement).blur();
      }
      return;
    }

    switch (e.key) {
      case ' ': {
        e.preventDefault();
        const playBtn = document.querySelector('[data-play-button]') as HTMLButtonElement | null;
        playBtn?.click();
        break;
      }
      case 'Enter': {
        e.preventDefault();
        const idx = getCurrentSegmentIndex();
        if (idx >= 0) {
          setEditingSegmentId(getSegments()[idx].id);
        }
        break;
      }
      case 'Escape': {
        e.preventDefault();
        if (exportMenuOpen) {
          exportMenuOpen = false;
        } else if (getEditingSegmentId()) {
          setEditingSegmentId(null);
          const ta = document.querySelector<HTMLTextAreaElement>('textarea:focus');
          ta?.blur();
        }
        break;
      }
      case 'ArrowLeft': {
        e.preventDefault();
        const delta = e.shiftKey ? 15000 : 5000;
        const newTime = Math.max(0, currentTimeMs - delta);
        waveformPane?.seekToTime(newTime);
        setCurrentTimeMs(newTime);
        break;
      }
      case 'ArrowRight': {
        e.preventDefault();
        const delta = e.shiftKey ? 15000 : 5000;
        const newTime = Math.min(durationMs, currentTimeMs + delta);
        waveformPane?.seekToTime(newTime);
        setCurrentTimeMs(newTime);
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        const curIdx = _getCurrentIndex();
        if (curIdx > 0) {
          const ms = seekToSegment(curIdx - 1);
          if (ms !== null) waveformPane?.seekToTime(ms);
        }
        break;
      }
      case 'ArrowDown': {
        e.preventDefault();
        const curIdx = _getCurrentIndex();
        const segs = getSegments();
        if (curIdx < segs.length - 1) {
          const ms = seekToSegment(curIdx + 1);
          if (ms !== null) waveformPane?.seekToTime(ms);
        }
        break;
      }
    }
  }

  function handleDividerMouseDown(e: MouseEvent) {
    e.preventDefault();
    setIsDraggingDivider(true);

    const startX = e.clientX;
    const startPct = leftPct;
    const containerWidth = containerEl?.clientWidth || 1;

    function onMouseMove(ev: MouseEvent) {
      const delta = ev.clientX - startX;
      const deltaPct = (delta / containerWidth) * 100;
      setLeftPaneWidthPct(startPct + deltaPct);
    }

    function onMouseUp() {
      setIsDraggingDivider(false);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  async function handleCopyTranscript() {
    const text = getFullTranscriptText();
    if (!text) {
      showWarning('No transcript to copy');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      copyTooltip = 'Copied!';
      setTimeout(() => (copyTooltip = ''), 1500);
    } catch {
      showError('Failed to copy transcript');
    }
  }

  async function handleRerun() {
    const revision = getRevision();
    if (revision > 1) {
      const ok = confirm('This will overwrite your edits. Continue?');
      if (!ok) return;
    }
    try {
      const res = await fetch(`/api/memos/${memoId}/reprocess?confirm=true`, { method: 'POST' });
      if (res.status === 409) {
        const body = await res.json();
        showError(body.detail ?? 'A job is already running');
        return;
      }
      if (!res.ok) {
        showError(`Re-run failed (${res.status})`);
        return;
      }
      const job = await res.json();
      connectEditorSSE(job.id);
      showSuccess('Re-running transcription…');
    } catch {
      showError('Failed to start re-run');
    }
  }

  async function handleRerunDiarization() {
    try {
      const res = await fetch(`/api/memos/${memoId}/regenerate-diarization`, { method: 'POST' });
      if (res.status === 409) {
        const body = await res.json();
        showError(body.detail ?? 'A job is already running');
        return;
      }
      if (!res.ok) {
        showError(`Diarization failed (${res.status})`);
        return;
      }
      const job = await res.json();
      connectEditorSSE(job.id);
      showSuccess('Re-running diarization…');
    } catch {
      showError('Failed to start diarization');
    }
  }

  function goBack() {
    goto('/');
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if loading}
  <div class="flex h-full items-center justify-center bg-[#F9F8F6]">
    <div class="flex flex-col items-center gap-12">
      <div class="h-10 w-10 animate-spin border-t border-l border-[#1A1A1A]"></div>
      <p class="text-xs uppercase tracking-[0.2em] font-sans text-[#1A1A1A]/60">Loading editor…</p>
    </div>
  </div>
{:else if error}
  <div class="flex h-full items-center justify-center p-12 bg-[#F9F8F6]">
    <div class="flex max-w-md flex-col items-center gap-12 text-center">
      <div class="border border-[#1A1A1A]/20 p-8 shadow-[0_2px_8px_rgba(0,0,0,0.02)]">
        <svg
          class="h-8 w-8 text-[#1A1A1A]"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </div>
      <p class="text-sm font-sans text-[#1A1A1A]">{error}</p>
      <div class="flex gap-8">
        <button
          onclick={() => memoId && initEditor(memoId)}
          class="flex items-center gap-4 border border-[#1A1A1A]/20 bg-[#F9F8F6] px-8 py-4 text-xs uppercase tracking-[0.2em] text-[#1A1A1A] transition-colors duration-500 ease-luxury hover:border-[#D4AF37] hover:text-[#D4AF37] rounded-none"
        >
          Retry
        </button>
        <button
          onclick={goBack}
          class="border border-[#1A1A1A]/20 bg-[#F9F8F6] px-8 py-4 text-xs uppercase tracking-[0.2em] text-[#1A1A1A] transition-colors duration-500 ease-luxury hover:border-[#D4AF37] hover:text-[#D4AF37] rounded-none"
        >
          Back to Library
        </button>
      </div>
    </div>
  </div>
{:else}
  <div class="flex h-full flex-col bg-[#F9F8F6] font-sans text-[#1A1A1A]">
    <!-- Floating toolbar -->
    <div class="flex shrink-0 items-center gap-8 border-b border-[#1A1A1A]/20 px-12 py-8">
      <button
        onclick={goBack}
        class="flex items-center gap-2 p-2 text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
        aria-label="Back to library"
      >
        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>

      <h1 class="min-w-0 flex-1 truncate text-2xl font-serif text-[#1A1A1A]">
        {memo?.title ?? 'Untitled'}
      </h1>

      <!-- Export -->
      <div class="relative">
        <button
          onclick={() => (exportMenuOpen = !exportMenuOpen)}
          disabled={!hasContent}
          class="px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] disabled:opacity-40 disabled:pointer-events-none rounded-none"
          title="Export transcript"
        >
          Export
        </button>
        {#if exportMenuOpen}
          <div class="absolute right-0 top-full mt-2 z-50">
            <ExportMenu {memoId} onclose={() => (exportMenuOpen = false)} />
          </div>
        {/if}
      </div>

      <!-- Copy -->
      <div class="relative">
        <button
          onclick={handleCopyTranscript}
          disabled={!hasContent}
          class="px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] disabled:opacity-40 disabled:pointer-events-none rounded-none"
          title="Copy transcript"
        >
          Copy
        </button>
        {#if copyTooltip}
          <span
            class="absolute -bottom-10 left-1/2 -translate-x-1/2 border border-[#1A1A1A]/20 bg-[#F9F8F6] px-4 py-2 text-xs uppercase tracking-[0.2em] text-[#D4AF37] whitespace-nowrap shadow-[0_2px_8px_rgba(0,0,0,0.02)]"
          >
            {copyTooltip}
          </span>
        {/if}
      </div>

      <!-- Re-run diarization (only when supported) -->
      {#if capabilities.speaker_diarization && hasContent}
        <button
          onclick={handleRerunDiarization}
          class="px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
          title="Re-run diarization"
        >
          Diarize
        </button>
      {/if}

      <!-- Re-run transcription -->
      <button
        onclick={handleRerun}
        class="px-6 py-2 text-xs uppercase tracking-[0.2em] text-[#1A1A1A]/60 transition-colors duration-500 ease-luxury hover:text-[#D4AF37] rounded-none"
        title="Re-run transcription"
      >
        Transcribe
      </button>
    </div>

    <!-- Two-pane layout -->
    <div bind:this={containerEl} class="relative flex flex-1 overflow-hidden p-0 gap-0">
      <!-- Left pane: Waveform & Transport -->
      <div
        class="flex shrink-0 flex-col overflow-hidden border-r border-[#1A1A1A]/20 bg-[#F9F8F6] shadow-[0_2px_8px_rgba(0,0,0,0.02)]"
        style="width: {leftPct}%"
      >
        <WaveformPane bind:this={waveformPane} />
      </div>

      <!-- Resizable divider -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="group relative z-10 flex w-8 shrink-0 cursor-col-resize items-center justify-center bg-[#F9F8F6] transition-colors duration-500 ease-luxury hover:bg-[#1A1A1A]/5 {isDragging
          ? 'bg-[#1A1A1A]/5'
          : ''}"
        onmousedown={handleDividerMouseDown}
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={leftPct}
        aria-valuemin={30}
        aria-valuemax={70}
      >
        <div
          class="h-full w-px bg-[#1A1A1A]/10 transition-colors duration-500 ease-luxury group-hover:bg-[#D4AF37] {isDragging
            ? 'bg-[#D4AF37]'
            : ''}"
        ></div>
      </div>

      <!-- Right pane: Transcript -->
      <div class="min-w-0 flex-1 overflow-hidden bg-[#F9F8F6]">
        <TranscriptPane bind:this={transcriptPane} />
      </div>
    </div>
  </div>
{/if}
