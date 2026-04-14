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

  // Initialize editor on mount
  $effect(() => {
    if (memoId) {
      initEditor(memoId);
    }
    return () => {
      cleanupEditor();
    };
  });

  // Flush pending saves before leaving the page
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

  // Connect transcript seek callback to waveform
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
    // Don't interfere with form elements (except Escape)
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
  <div class="flex h-full items-center justify-center">
    <div class="flex flex-col items-center gap-4">
      <div class="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent"></div>
      <p class="text-sm text-text-secondary">Loading editor…</p>
    </div>
  </div>
{:else if error}
  <div class="flex h-full items-center justify-center px-4">
    <div class="flex max-w-md flex-col items-center gap-4 text-center">
      <div class="rounded-full bg-error/10 p-4">
        <svg
          class="h-8 w-8 text-error"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </div>
      <p class="text-sm text-text-secondary">{error}</p>
      <div class="flex gap-3">
        <button
          onclick={() => memoId && initEditor(memoId)}
          class="flex items-center gap-2 rounded-lg border border-border bg-surface-800 px-4 py-2 text-sm text-text-primary transition-colors hover:bg-surface-700"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="23,4 23,10 17,10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          Retry
        </button>
        <button
          onclick={goBack}
          class="rounded-lg border border-border bg-surface-800 px-4 py-2 text-sm text-text-primary transition-colors hover:bg-surface-700"
        >
          Back to Library
        </button>
      </div>
    </div>
  </div>
{:else}
  <div class="flex h-full flex-col">
    <!-- Floating toolbar -->
    <div class="flex shrink-0 items-center gap-3 border-b border-border bg-surface-800 px-4 py-2">
      <button
        onclick={goBack}
        class="flex items-center gap-1 rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary"
        aria-label="Back to library"
      >
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>

      <h1 class="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">
        {memo?.title ?? 'Untitled'}
      </h1>

      <!-- Export -->
      <div class="relative">
        <button
          onclick={() => (exportMenuOpen = !exportMenuOpen)}
          disabled={!hasContent}
          class="rounded-md px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary disabled:opacity-40 disabled:pointer-events-none"
          title="Export transcript"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7,10 12,15 17,10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        </button>
        {#if exportMenuOpen}
          <ExportMenu {memoId} onclose={() => (exportMenuOpen = false)} />
        {/if}
      </div>

      <!-- Copy -->
      <div class="relative">
        <button
          onclick={handleCopyTranscript}
          disabled={!hasContent}
          class="rounded-md px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary disabled:opacity-40 disabled:pointer-events-none"
          title="Copy transcript"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        </button>
        {#if copyTooltip}
          <span
            class="absolute -top-7 left-1/2 -translate-x-1/2 rounded bg-surface-600 px-2 py-1 text-xs text-accent whitespace-nowrap"
          >
            {copyTooltip}
          </span>
        {/if}
      </div>

      <!-- Re-run diarization (only when supported) -->
      {#if capabilities.speaker_diarization && hasContent}
        <button
          onclick={handleRerunDiarization}
          class="rounded-md px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary"
          title="Re-run diarization"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </button>
      {/if}

      <!-- Re-run transcription -->
      <button
        onclick={handleRerun}
        class="rounded-md px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-700 hover:text-text-primary"
        title="Re-run transcription"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23,4 23,10 17,10" />
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
      </button>
    </div>

    <!-- Two-pane layout -->
    <div bind:this={containerEl} class="relative flex flex-1 overflow-hidden">
      <!-- Left pane: Waveform & Transport -->
      <div
        class="flex shrink-0 flex-col overflow-hidden border-r border-border"
        style="width: {leftPct}%"
      >
        <WaveformPane bind:this={waveformPane} />
      </div>

      <!-- Resizable divider -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="group relative z-10 flex w-2 shrink-0 cursor-col-resize items-center justify-center bg-surface-800 transition-colors hover:bg-accent/20 {isDragging
          ? 'bg-accent/20'
          : ''}"
        onmousedown={handleDividerMouseDown}
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={leftPct}
        aria-valuemin={30}
        aria-valuemax={70}
      >
        <div
          class="h-8 w-0.5 rounded-full bg-surface-500 transition-colors group-hover:bg-accent {isDragging
            ? 'bg-accent'
            : ''}"
        ></div>
      </div>

      <!-- Right pane: Transcript -->
      <div class="min-w-0 flex-1 overflow-hidden">
        <TranscriptPane bind:this={transcriptPane} />
      </div>
    </div>
  </div>
{/if}
