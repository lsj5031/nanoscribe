<script lang="ts">
  import { goto } from '$app/navigation';
  import { getCapabilities, getCapabilitiesLoading } from '$lib/stores/capabilities.svelte';
  import {
    getReadiness,
    fetchReadiness,
    startReadinessPolling,
    stopReadinessPolling,
    type ModelReadiness
  } from '$lib/stores/readiness.svelte';
  import { isMediaRecorderSupported } from '$lib/stores/recording.svelte';
  import { uploadFiles } from '$lib/stores/upload.svelte';
  import MemoCard from '$lib/components/MemoCard.svelte';
  import LibraryControls from '$lib/components/LibraryControls.svelte';
  import RecordingModal from '$lib/components/RecordingModal.svelte';
  import {
    getMemos,
    getTotal,
    getLoading,
    getViewMode,
    fetchMemos,
    cleanup,
    setQuery,
    getQuery,
    getSort,
    getStatusFilter
  } from '$lib/stores/library.svelte';

  let fileInput: HTMLInputElement | undefined = $state();
  let searchInput: HTMLInputElement | undefined = $state();
  let recordingModal: RecordingModal | undefined = $state();

  const memos = $derived(getMemos());
  const total = $derived(getTotal());
  const loading = $derived(getLoading());
  const viewMode = $derived(getViewMode());
  const capabilitiesLoading = $derived(getCapabilitiesLoading());
  const capabilities = $derived(getCapabilities());
  const readiness = $derived(getReadiness());
  const isEmpty = $derived(memos.length === 0 && !loading);
  const query = $derived(getQuery());
  const sort = $derived(getSort());
  const statusFilter = $derived(getStatusFilter());

  // First-run detection via localStorage
  const hasVisitedBefore = $state(
    typeof localStorage !== 'undefined' && localStorage.getItem('nanoscribe-visited') === 'true'
  );

  const isFirstRun = $derived(isEmpty && !hasVisitedBefore);

  // Mark as visited when user sees the normal empty state or has memos
  $effect(() => {
    if (typeof localStorage !== 'undefined' && (memos.length > 0 || capabilities.ready)) {
      localStorage.setItem('nanoscribe-visited', 'true');
    }
  });

  // Any model downloading?
  const anyDownloading = $derived(
    Object.values(readiness.models || {}).some((m: ModelReadiness) => m.downloading)
  );

  // Recording only if both backend capability and browser MediaRecorder support
  const canRecord = $derived(capabilities.recording && isMediaRecorderSupported());

  // Fetch memos on mount and when returning to the page
  $effect(() => {
    fetchMemos();
    return () => cleanup();
  });

  // Re-fetch when sort/filter changes
  $effect(() => {
    // These reads make the effect reactive to changes
    sort;
    statusFilter;
    fetchMemos();
  });

  // Readiness polling: start when capabilities say not ready
  $effect(() => {
    if (!capabilitiesLoading && !capabilities.ready && isEmpty) {
      startReadinessPolling(5000);
    }
    return () => stopReadinessPolling();
  });

  function openFilePicker() {
    fileInput?.click();
  }

  function handleFileChange(e: Event) {
    const target = e.target as HTMLInputElement;
    if (target.files?.length) {
      uploadFiles(Array.from(target.files));
      target.value = '';
    }
  }

  function handleSearchInput(e: Event) {
    const target = e.target as HTMLInputElement;
    setQuery(target.value);
  }

  function handleSearchClear() {
    setQuery('');
    if (searchInput) searchInput.value = '';
  }
</script>

<!-- Hidden file input -->
<input
  bind:this={fileInput}
  type="file"
  accept=".wav,.mp3,.m4a,.aac,.webm,.ogg,.opus"
  multiple
  onchange={handleFileChange}
  class="hidden"
  aria-hidden="true"
/>

<div class="flex h-full flex-col">
  {#if capabilitiesLoading}
    <!-- Loading capabilities -->
    <div class="flex flex-1 items-center justify-center">
      <div class="flex flex-col items-center gap-4">
        <div
          class="h-10 w-10 animate-spin rounded-none border-2 border-text-primary/20 border-t-accent duration-500 ease-luxury"
        ></div>
        <p class="text-xs uppercase tracking-[0.2em] text-text-secondary">Loading…</p>
      </div>
    </div>
  {:else if isEmpty && !capabilities.ready}
    <!-- Readiness card: models not ready and no memos -->
    <div class="flex flex-1 items-center justify-center px-4">
      <div
        class="flex max-w-md w-full flex-col items-center gap-6 rounded-none border-t border-text-primary/20 bg-transparent p-8 text-center shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:bg-text-primary/5 duration-500 ease-luxury"
      >
        <div class="rounded-none bg-accent/10 p-4">
          {#if anyDownloading}
            <div
              class="h-8 w-8 animate-spin rounded-none border-2 border-accent/30 border-t-accent"
            ></div>
          {:else}
            <svg
              class="h-8 w-8 text-warning"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          {/if}
        </div>

        <div>
          <h2 class="text-5xl font-serif leading-[0.9] text-text-primary">
            {anyDownloading ? 'Models are being downloaded…' : 'Setup required'}
          </h2>
          <p class="mt-4 text-sm text-text-secondary">
            {anyDownloading
              ? 'NanoScribe is downloading the required models. This may take a few minutes on first run.'
              : 'Required models are not yet available. Make sure the server has internet access to download models on first launch.'}
          </p>
        </div>

        <!-- Per-model status list -->
        {#if Object.keys(readiness.models).length > 0}
          <div class="w-full space-y-2 text-left">
            {#each Object.entries(readiness.models) as [key, model]}
              <div
                class="flex items-center justify-between rounded-none border-t border-text-primary/10 bg-transparent px-3 py-2 hover:bg-text-primary/5 duration-500 ease-luxury"
              >
                <div class="flex items-center gap-2">
                  {#if model.loaded}
                    <svg
                      class="h-4 w-4 text-success"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  {:else if model.downloading}
                    <div
                      class="h-4 w-4 animate-spin rounded-none border-2 border-accent/30 border-t-accent"
                    ></div>
                  {:else}
                    <svg
                      class="h-4 w-4 text-text-muted"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <circle cx="12" cy="12" r="10" />
                    </svg>
                  {/if}
                  <span class="text-sm text-text-secondary">{model.name}</span>
                </div>
                <span
                  class="text-xs uppercase tracking-[0.2em] {model.loaded
                    ? 'text-success'
                    : model.downloading
                      ? 'text-accent'
                      : 'text-text-muted'}"
                >
                  {model.loaded ? 'Ready' : model.downloading ? 'Downloading' : 'Not cached'}
                </span>
              </div>
            {/each}
          </div>
        {/if}

        <!-- GPU status -->
        <div class="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-text-muted">
          {#if readiness.gpu_available}
            <span class="h-2 w-2 rounded-none bg-success"></span>
            <span>GPU available ({readiness.device})</span>
          {:else}
            <span class="h-2 w-2 rounded-none bg-warning"></span>
            <span>CPU mode — GPU not detected</span>
          {/if}
        </div>
      </div>
    </div>
  {:else if isEmpty}
    <!-- Empty state -->
    <div class="flex flex-1 items-center justify-center px-4">
      <div class="flex max-w-lg flex-col items-center gap-8">
        {#if isFirstRun}
          <!-- First-run welcome message -->
          <div class="text-center">
            <h1 class="text-7xl font-serif leading-[0.9] text-text-primary">
              Welcome to NanoScribe
            </h1>
            <p class="mt-4 text-text-secondary">
              Your local voice transcription assistant, powered by FunASR.
            </p>
          </div>

          <div
            class="w-full max-w-sm space-y-4 rounded-none border-t border-text-primary/20 bg-transparent p-6 shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:bg-text-primary/5 duration-500 ease-luxury"
          >
            <h2 class="text-xs uppercase tracking-[0.2em] text-text-primary">Quick Start</h2>
            <ol class="space-y-3 text-sm text-text-secondary">
              <li class="flex gap-2">
                <span class="shrink-0 font-medium text-accent">1.</span>
                <span>Drag &amp; drop an audio file or click to upload</span>
              </li>
              <li class="flex gap-2">
                <span class="shrink-0 font-medium text-accent">2.</span>
                <span>Watch real-time transcription progress</span>
              </li>
              <li class="flex gap-2">
                <span class="shrink-0 font-medium text-accent">3.</span>
                <span>Edit transcripts with synchronized playback</span>
              </li>
              <li class="flex gap-2">
                <span class="shrink-0 font-medium text-accent">4.</span>
                <span>Export as TXT, JSON, or SRT</span>
              </li>
            </ol>
            <p class="pt-2 text-xs uppercase tracking-[0.2em] text-text-muted">
              Supported formats: WAV, MP3, M4A, AAC, WebM, OGG, OPUS
            </p>
          </div>

          <button
            onclick={openFilePicker}
            class="flex items-center gap-2 rounded-none bg-text-primary px-6 py-3 text-xs uppercase tracking-[0.2em] text-surface-900 duration-500 ease-luxury hover:bg-accent hover:text-white"
          >
            <svg
              class="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Upload your first audio file
          </button>
        {:else}
          <!-- Animated waveform -->
          <div class="flex items-end gap-1">
            {#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as bar}
              <div
                class="w-1.5 rounded-none bg-accent"
                style="height: {12 +
                  Math.sin(bar * 0.8) * 16}px; animation: pulse 2s ease-in-out {bar *
                  0.1}s infinite alternate;"
              ></div>
            {/each}
          </div>

          <div class="text-center">
            <h1 class="text-6xl font-serif leading-[0.9] text-text-primary">
              Drop voice memo here
            </h1>
            <p class="mt-4 text-text-secondary">Processed locally with FunASR</p>
          </div>

          <!-- Upload area -->
          <button
            onclick={openFilePicker}
            class="flex w-full max-w-sm flex-col items-center gap-3 rounded-none border-t border-text-primary/20 bg-transparent p-8 shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:bg-text-primary/5 duration-500 ease-luxury group"
          >
            <svg
              class="h-10 w-10 text-text-muted group-hover:text-accent duration-500 ease-luxury"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17,8 12,3 7,8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p
              class="text-sm text-text-muted group-hover:text-text-primary duration-500 ease-luxury"
            >
              Drop audio files here or click to upload
            </p>
            <p
              class="text-xs uppercase tracking-[0.2em] text-text-muted group-hover:text-accent duration-500 ease-luxury"
            >
              WAV, MP3, M4A, AAC, WebM, OGG, OPUS
            </p>
          </button>
        {/if}

        {#if canRecord}
          <button
            onclick={() => recordingModal?.open()}
            class="flex items-center gap-2 rounded-none border-b border-text-primary bg-transparent px-5 py-2.5 text-xs uppercase tracking-[0.2em] text-text-secondary duration-500 ease-luxury hover:border-accent hover:text-accent"
          >
            <svg class="h-4 w-4 text-error" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="12" r="8" />
            </svg>
            Record from microphone
          </button>
        {/if}
      </div>
    </div>
  {:else}
    <!-- Populated state -->
    <div class="flex flex-1 flex-col overflow-hidden">
      <!-- Toolbar -->
      <div class="flex items-center gap-4 border-b border-text-primary/20 px-6 py-4">
        <!-- Search -->
        <div class="relative flex-1 max-w-md">
          <svg
            class="absolute left-0 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
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
            value={query}
            oninput={handleSearchInput}
            placeholder="Search memos…"
            class="w-full rounded-none border-b border-text-primary bg-transparent py-2 pl-8 pr-8 text-sm text-text-primary placeholder:font-serif placeholder:italic placeholder:text-text-muted outline-none duration-500 ease-luxury focus:border-accent"
            aria-label="Search memos"
          />
          {#if query}
            <button
              onclick={handleSearchClear}
              class="absolute right-0 top-1/2 -translate-y-1/2 text-text-muted duration-500 ease-luxury hover:text-accent"
              aria-label="Clear search"
            >
              <svg
                class="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          {/if}
        </div>

        <!-- Controls -->
        <LibraryControls />

        {#if canRecord}
          <button
            onclick={() => recordingModal?.open()}
            class="flex items-center gap-2 rounded-none border-b border-text-primary bg-transparent px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-text-secondary duration-500 ease-luxury hover:border-accent hover:text-accent"
            aria-label="Record audio"
          >
            <svg class="h-3.5 w-3.5 text-error" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="12" r="8" />
            </svg>
            <span>Record</span>
          </button>
        {/if}

        <!-- Memo count -->
        <span class="shrink-0 text-xs uppercase tracking-[0.2em] text-text-muted">
          {total} memo{total !== 1 ? 's' : ''}
        </span>
      </div>

      <!-- Content area -->
      <div class="flex-1 overflow-y-auto p-6">
        {#if loading && memos.length === 0}
          <div class="flex h-full items-center justify-center">
            <div
              class="h-8 w-8 animate-spin rounded-none border-2 border-text-primary/20 border-t-accent duration-500 ease-luxury"
            ></div>
          </div>
        {:else if memos.length === 0}
          <!-- No results after filter/search -->
          <div class="flex h-full flex-col items-center justify-center gap-6">
            <svg
              class="h-12 w-12 text-text-muted"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <div class="text-center">
              <p class="text-4xl font-serif leading-[0.9] text-text-primary">No memos found</p>
              <p class="mt-4 text-sm text-text-secondary">
                {query ? `No results for "${query}"` : 'No memos match the current filter'}
              </p>
            </div>
          </div>
        {:else if viewMode === 'grid'}
          <!-- Grid view -->
          <div class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {#each memos as memo (memo.id)}
              <MemoCard {memo} {viewMode} />
            {/each}
          </div>
        {:else}
          <!-- List view -->
          <div class="flex flex-col gap-4">
            {#each memos as memo (memo.id)}
              <MemoCard {memo} {viewMode} />
            {/each}
          </div>
        {/if}

        <!-- Loading indicator for pagination -->
        {#if loading && memos.length > 0}
          <div class="flex justify-center py-6">
            <div
              class="h-6 w-6 animate-spin rounded-none border-2 border-text-primary/20 border-t-accent duration-500 ease-luxury"
            ></div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Floating upload button -->
    <button
      onclick={openFilePicker}
      class="fixed bottom-8 right-8 z-30 flex h-16 w-16 items-center justify-center rounded-none bg-text-primary text-surface-900 shadow-[0_2px_8px_rgba(0,0,0,0.02)] duration-500 ease-luxury hover:bg-accent hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:scale-105"
      aria-label="Upload audio file"
    >
      <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
    </button>
  {/if}
</div>

<RecordingModal bind:this={recordingModal} />

<style>
  @keyframes pulse {
    from {
      opacity: 0.4;
    }
    to {
      opacity: 1;
    }
  }
</style>
