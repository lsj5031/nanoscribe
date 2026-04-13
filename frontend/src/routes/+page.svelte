<script lang="ts">
  import { goto } from '$app/navigation';
  import { getCapabilities, getCapabilitiesLoading } from '$lib/stores/capabilities.svelte';
  import { uploadFiles } from '$lib/stores/upload.svelte';
  import MemoCard from '$lib/components/MemoCard.svelte';
  import LibraryControls from '$lib/components/LibraryControls.svelte';
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

  const memos = $derived(getMemos());
  const total = $derived(getTotal());
  const loading = $derived(getLoading());
  const viewMode = $derived(getViewMode());
  const capabilitiesLoading = $derived(getCapabilitiesLoading());
  const capabilities = $derived(getCapabilities());
  const isEmpty = $derived(memos.length === 0 && !loading);
  const query = $derived(getQuery());
  const sort = $derived(getSort());
  const statusFilter = $derived(getStatusFilter());

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
          class="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent"
        ></div>
        <p class="text-text-secondary">Loading…</p>
      </div>
    </div>
  {:else if isEmpty && !capabilities.ready}
    <!-- Readiness card: models not ready and no memos -->
    <div class="flex flex-1 items-center justify-center px-4">
      <div
        class="flex max-w-md flex-col items-center gap-6 rounded-2xl border border-border bg-surface-800 p-8 text-center"
      >
        <div class="rounded-full bg-accent-muted p-4">
          <svg
            class="h-8 w-8 text-accent"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"
            />
          </svg>
        </div>
        <div>
          <h2 class="text-xl font-semibold text-text-primary">Setting Up</h2>
          <p class="mt-2 text-sm text-text-secondary">
            NanoScribe is preparing the transcription engine. This may take a few minutes on first
            run while models are downloaded.
          </p>
        </div>
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <div class="h-2 w-2 animate-pulse rounded-full bg-accent"></div>
          <span>Checking model status…</span>
        </div>
      </div>
    </div>
  {:else if isEmpty}
    <!-- Empty state -->
    <div class="flex flex-1 items-center justify-center px-4">
      <div class="flex max-w-lg flex-col items-center gap-8">
        <!-- Animated waveform -->
        <div class="flex items-end gap-1">
          {#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as bar}
            <div
              class="w-1.5 rounded-full bg-accent"
              style="height: {12 +
                Math.sin(bar * 0.8) * 16}px; animation: pulse 2s ease-in-out {bar *
                0.1}s infinite alternate;"
            ></div>
          {/each}
        </div>

        <div class="text-center">
          <h1 class="text-2xl font-semibold text-text-primary">Drop voice memo here</h1>
          <p class="mt-2 text-text-secondary">Processed locally with FunASR</p>
        </div>

        <!-- Upload area -->
        <button
          onclick={openFilePicker}
          class="flex w-full max-w-sm flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border p-8 transition-colors hover:border-accent hover:bg-accent-muted/30"
        >
          <svg
            class="h-10 w-10 text-text-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17,8 12,3 7,8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <p class="text-sm text-text-muted">Drop audio files here or click to upload</p>
          <p class="text-xs text-text-muted">WAV, MP3, M4A, AAC, WebM, OGG, OPUS</p>
        </button>

        {#if capabilities.recording}
          <button
            class="flex items-center gap-2 rounded-lg border border-border bg-surface-800 px-5 py-2.5 text-sm text-text-secondary transition-colors hover:border-accent/40 hover:text-text-primary"
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
      <div class="flex items-center gap-3 border-b border-border px-4 py-3">
        <!-- Search -->
        <div class="relative flex-1">
          <svg
            class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
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
            class="w-full rounded-lg border border-border bg-surface-700 py-2 pl-9 pr-9 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent"
            aria-label="Search memos"
          />
          {#if query}
            <button
              onclick={handleSearchClear}
              class="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
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

        <!-- Memo count -->
        <span class="shrink-0 text-xs text-text-muted">
          {total} memo{total !== 1 ? 's' : ''}
        </span>
      </div>

      <!-- Content area -->
      <div class="flex-1 overflow-y-auto p-4">
        {#if loading && memos.length === 0}
          <div class="flex h-full items-center justify-center">
            <div
              class="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent"
            ></div>
          </div>
        {:else if memos.length === 0}
          <!-- No results after filter/search -->
          <div class="flex h-full flex-col items-center justify-center gap-4">
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
              <p class="text-lg font-medium text-text-primary">No memos found</p>
              <p class="mt-1 text-sm text-text-secondary">
                {query ? `No results for "${query}"` : 'No memos match the current filter'}
              </p>
            </div>
          </div>
        {:else if viewMode === 'grid'}
          <!-- Grid view -->
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {#each memos as memo (memo.id)}
              <MemoCard {memo} {viewMode} />
            {/each}
          </div>
        {:else}
          <!-- List view -->
          <div class="flex flex-col gap-2">
            {#each memos as memo (memo.id)}
              <MemoCard {memo} {viewMode} />
            {/each}
          </div>
        {/if}

        <!-- Loading indicator for pagination -->
        {#if loading && memos.length > 0}
          <div class="flex justify-center py-4">
            <div
              class="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent"
            ></div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Floating upload button -->
    <button
      onclick={openFilePicker}
      class="fixed bottom-6 right-6 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-surface-900 shadow-lg transition-all hover:bg-accent-hover hover:shadow-xl hover:scale-105 active:scale-95"
      aria-label="Upload audio file"
    >
      <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
    </button>
  {/if}
</div>

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
