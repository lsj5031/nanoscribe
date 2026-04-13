<!--
  LibraryControls: Grid/list toggle, sort dropdown, and status filter for the library.
-->
<script lang="ts">
  import {
    getViewMode,
    setViewMode,
    getSort,
    setSort,
    getStatusFilter,
    setStatusFilter,
    type ViewMode,
    type SortMode
  } from '$lib/stores/library.svelte';

  let sortOpen = $state(false);
  let filterOpen = $state(false);

  const viewMode = $derived(getViewMode());
  const sort = $derived(getSort());
  const statusFilter = $derived(getStatusFilter());

  function toggleSort() {
    sortOpen = !sortOpen;
    filterOpen = false;
  }

  function toggleFilter() {
    filterOpen = !filterOpen;
    sortOpen = false;
  }

  function selectSort(mode: SortMode) {
    setSort(mode);
    sortOpen = false;
  }

  function selectStatus(status: string | null) {
    setStatusFilter(status);
    filterOpen = false;
  }

  function closeDropdowns() {
    sortOpen = false;
    filterOpen = false;
  }

  const statusOptions = [
    { value: null, label: 'All Statuses' },
    { value: 'completed', label: 'Completed' },
    { value: 'failed', label: 'Failed' },
    { value: 'queued', label: 'Queued' },
    { value: 'transcribing', label: 'Transcribing' },
    { value: 'cancelled', label: 'Cancelled' }
  ];
</script>

<svelte:window onclick={closeDropdowns} />

<div class="flex items-center gap-2">
  <!-- Grid/List toggle -->
  <div class="flex rounded-lg border border-border bg-surface-800 p-0.5">
    <button
      onclick={() => setViewMode('grid')}
      class="rounded-md p-1.5 transition-colors {viewMode === 'grid'
        ? 'bg-surface-600 text-text-primary'
        : 'text-text-muted hover:text-text-secondary'}"
      aria-label="Grid view"
      aria-pressed={viewMode === 'grid'}
    >
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
      </svg>
    </button>
    <button
      onclick={() => setViewMode('list')}
      class="rounded-md p-1.5 transition-colors {viewMode === 'list'
        ? 'bg-surface-600 text-text-primary'
        : 'text-text-muted hover:text-text-secondary'}"
      aria-label="List view"
      aria-pressed={viewMode === 'list'}
    >
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
      </svg>
    </button>
  </div>

  <!-- Sort dropdown -->
  <div class="relative">
    <button
      onclick={(e) => {
        e.stopPropagation();
        toggleSort();
      }}
      class="flex items-center gap-1.5 rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-accent/40 hover:text-text-primary"
      aria-label="Sort"
    >
      <svg
        class="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M3 6h18M6 12h12M9 18h6" />
      </svg>
      <span>{sort === 'recent' ? 'Recent' : 'Duration'}</span>
    </button>
    {#if sortOpen}
      <div
        class="absolute right-0 top-full z-10 mt-1 min-w-[140px] rounded-lg border border-border bg-surface-800 py-1 shadow-xl"
      >
        <button
          onclick={(e) => {
            e.stopPropagation();
            selectSort('recent');
          }}
          class="flex w-full items-center gap-2 px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-surface-700 hover:text-text-primary {sort ===
          'recent'
            ? 'text-accent'
            : ''}"
        >
          {#if sort === 'recent'}
            <svg class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor"
              ><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" /></svg
            >
          {:else}
            <span class="w-3"></span>
          {/if}
          Most Recent
        </button>
        <button
          onclick={(e) => {
            e.stopPropagation();
            selectSort('duration');
          }}
          class="flex w-full items-center gap-2 px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-surface-700 hover:text-text-primary {sort ===
          'duration'
            ? 'text-accent'
            : ''}"
        >
          {#if sort === 'duration'}
            <svg class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor"
              ><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" /></svg
            >
          {:else}
            <span class="w-3"></span>
          {/if}
          Longest Duration
        </button>
      </div>
    {/if}
  </div>

  <!-- Status filter -->
  <div class="relative">
    <button
      onclick={(e) => {
        e.stopPropagation();
        toggleFilter();
      }}
      class="flex items-center gap-1.5 rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs transition-colors hover:border-accent/40 {statusFilter
        ? 'border-accent/40 text-accent'
        : 'text-text-secondary hover:text-text-primary'}"
      aria-label="Filter by status"
    >
      <svg
        class="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polygon points="22,3 2,3 10,12.46 10,19 14,21 14,12.46" />
      </svg>
      <span
        >{statusFilter
          ? (statusOptions.find((o) => o.value === statusFilter)?.label ?? 'Filter')
          : 'Status'}</span
      >
    </button>
    {#if filterOpen}
      <div
        class="absolute right-0 top-full z-10 mt-1 min-w-[160px] rounded-lg border border-border bg-surface-800 py-1 shadow-xl"
      >
        {#each statusOptions as option}
          <button
            onclick={(e) => {
              e.stopPropagation();
              selectStatus(option.value);
            }}
            class="flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-surface-700 {statusFilter ===
            option.value
              ? 'text-accent'
              : 'text-text-secondary hover:text-text-primary'}"
          >
            {#if statusFilter === option.value}
              <svg class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor"
                ><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" /></svg
              >
            {:else}
              <span class="w-3"></span>
            {/if}
            {option.label}
          </button>
        {/each}
      </div>
    {/if}
  </div>
</div>
