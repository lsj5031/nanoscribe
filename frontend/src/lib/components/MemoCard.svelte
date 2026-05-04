<!--
  MemoCard: Displays a memo in either grid or list layout.
  Shows waveform thumbnail, title, duration, speaker count, last edited, status badge.
  Failed cards show a retry button.
  Clicking the card navigates to the editor.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import WaveformThumbnail from './WaveformThumbnail.svelte';
  import {
    formatDuration,
    formatRelativeTime,
    getStatusColor,
    getStatusLabel,
    retryMemo,
    deleteMemo,
    type MemoCard as MemoCardType,
    type ViewMode
  } from '$lib/stores/library.svelte';

  interface Props {
    memo: MemoCardType;
    viewMode: ViewMode;
  }

  let { memo, viewMode }: Props = $props();

  let retrying = $state(false);
  let showDeleteConfirm = $state(false);

  function handleClick(e: MouseEvent) {
    // Don't navigate if clicking on action buttons
    const target = e.target as HTMLElement;
    if (target.closest('button') || target.closest('[data-action]')) return;
    goto(`/memos/${memo.id}`);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') goto(`/memos/${memo.id}`);
  }

  async function handleRetry(e: MouseEvent) {
    e.stopPropagation();
    retrying = true;
    await retryMemo(memo.id);
    retrying = false;
  }

  function handleDeleteClick(e: MouseEvent) {
    e.stopPropagation();
    showDeleteConfirm = true;
  }

  async function confirmDelete() {
    showDeleteConfirm = false;
    await deleteMemo(memo.id);
  }

  function cancelDelete() {
    showDeleteConfirm = false;
  }

  const isFailed = $derived(memo.status === 'failed' || memo.status === 'cancelled');
  const isActive = $derived(
    memo.status === 'queued' ||
      memo.status === 'preprocessing' ||
      memo.status === 'transcribing' ||
      memo.status === 'diarizing' ||
      memo.status === 'finalizing'
  );
  const progressPct = $derived(Math.round(memo.progress * 100));
</script>

<!-- GRID VIEW -->
{#if viewMode === 'grid'}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_interactive_supports_focus -->
  <div
    onclick={handleClick}
    tabindex="0"
    onkeydown={handleKeydown}
    class="group relative flex cursor-pointer flex-col overflow-hidden rounded-none border-t border-text-primary/20 bg-transparent shadow-[0_2px_8px_rgba(0,0,0,0.02)] duration-500 ease-luxury hover:bg-text-primary/5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)]"
    role="link"
  >
    <!-- Waveform area -->
    <div class="relative h-24 w-full overflow-hidden bg-transparent">
      {#if memo.waveform_url}
        <WaveformThumbnail
          url={memo.waveform_url}
          class="h-full w-full opacity-60 grayscale duration-[1500ms] ease-luxury group-hover:scale-105 group-hover:grayscale-0"
        />
      {:else}
        <!-- Placeholder bars for memos without waveform -->
        <div class="flex h-full items-end justify-center gap-0.5 px-2 pb-2 pt-4">
          {#each Array(40) as _, i}
            {@const h = 8 + Math.sin(i * 0.5) * 12 + Math.cos(i * 0.3) * 8}
            <div
              class="flex-1 rounded-none bg-text-primary/20 duration-[1500ms] ease-luxury group-hover:bg-accent/40"
              style="height: {h}px;"
            ></div>
          {/each}
        </div>
      {/if}

      <!-- Status badge (hidden for active jobs — shown via progress bar instead) -->
      {#if !isActive}
        <span
          class="absolute right-3 top-3 rounded-none border border-text-primary/20 bg-surface-900/80 px-2 py-1 text-xs uppercase tracking-[0.2em] font-medium {getStatusColor(
            memo.status
          )}"
        >
          {getStatusLabel(memo.status)}
        </span>
      {/if}

      <!-- Active indicator -->
      {#if isActive}
        <div class="absolute left-3 top-3 flex items-center gap-2">
          <div class="h-2 w-2 animate-pulse rounded-none bg-accent"></div>
          <span class="text-xs uppercase tracking-[0.2em] text-accent font-medium">
            {getStatusLabel(memo.status)}
          </span>
        </div>
      {/if}
    </div>

    <!-- Progress bar for active jobs -->
    {#if isActive}
      <div class="h-1 w-full overflow-hidden bg-text-primary/10">
        {#if progressPct > 0 && progressPct < 20}
          <!-- Indeterminate shimmer for early progress (remote transcription has no per-chunk updates) -->
          <div class="relative h-full w-full">
            <div
              class="h-full bg-accent/60 transition-all duration-500 ease-luxury"
              style="width: {progressPct}%"
            ></div>
            <div
              class="absolute inset-0 h-full w-full animate-pulse bg-gradient-to-r from-accent/0 via-accent/40 to-accent/0"
            ></div>
          </div>
        {:else}
          <div
            class="h-full bg-accent transition-all duration-500 ease-luxury"
            style="width: {progressPct}%"
          ></div>
        {/if}
      </div>
    {/if}

    <!-- Content -->
    <div class="flex flex-1 flex-col gap-3 p-5">
      <h3
        class="truncate text-5xl font-serif leading-[0.9] text-text-primary duration-500 ease-luxury group-hover:text-accent"
      >
        {memo.title}
      </h3>
      <div class="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-text-muted">
        <span>{formatDuration(memo.duration_ms)}</span>
        {#if memo.speaker_count > 0}
          <span>{memo.speaker_count} speaker{memo.speaker_count > 1 ? 's' : ''}</span>
        {/if}
      </div>
      <div class="mt-auto pt-2 text-xs uppercase tracking-[0.2em] text-text-muted">
        {formatRelativeTime(memo.updated_at)}
      </div>
    </div>

    <!-- Actions -->
    {#if isFailed}
      <div class="flex flex-col gap-2 border-t border-text-primary/20 px-5 py-3">
        {#if memo.error_message}
          <p class="text-xs text-error/80 line-clamp-2" title={memo.error_message}>{memo.error_message}</p>
        {/if}
        <div class="flex gap-2">
          <button
            onclick={handleRetry}
            disabled={retrying}
            class="flex-1 rounded-none bg-transparent px-2 py-1 text-xs uppercase tracking-[0.2em] font-medium text-text-primary duration-500 ease-luxury hover:text-accent disabled:opacity-50"
            data-action="retry"
            aria-label="Retry transcription"
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
          <button
            onclick={handleDeleteClick}
            class="rounded-none px-2 py-1 text-xs uppercase tracking-[0.2em] text-text-muted duration-500 ease-luxury hover:text-error"
            data-action="delete"
            aria-label="Delete memo"
          >
            Delete
          </button>
        </div>
      </div>
    {:else if memo.status === 'completed'}
      <div
        class="flex justify-end border-t border-text-primary/20 px-5 py-2 opacity-0 transition-opacity duration-500 ease-luxury group-hover:opacity-100"
      >
        <button
          onclick={handleDeleteClick}
          class="rounded-none p-1 text-xs uppercase tracking-[0.2em] text-text-muted duration-500 ease-luxury hover:text-error"
          data-action="delete"
          aria-label="Delete memo"
        >
          Delete
        </button>
      </div>
    {/if}
  </div>
{:else}
  <!-- LIST VIEW -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_interactive_supports_focus -->
  <div
    onclick={handleClick}
    tabindex="0"
    onkeydown={handleKeydown}
    class="group flex cursor-pointer items-center gap-6 rounded-none border-t border-text-primary/20 bg-transparent px-6 py-4 shadow-[0_2px_8px_rgba(0,0,0,0.02)] duration-500 ease-luxury hover:bg-text-primary/5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)]"
    role="link"
  >
    <!-- Waveform thumbnail -->
    <div class="h-10 w-24 shrink-0 overflow-hidden rounded-none bg-transparent">
      {#if memo.waveform_url}
        <WaveformThumbnail
          url={memo.waveform_url}
          class="h-full w-full opacity-60 grayscale duration-[1500ms] ease-luxury group-hover:scale-105 group-hover:grayscale-0"
        />
      {:else}
        <div class="flex h-full items-end justify-center gap-px px-1 pb-1 pt-2">
          {#each Array(20) as _, i}
            {@const h = 4 + Math.sin(i * 0.5) * 6}
            <div
              class="flex-1 rounded-none bg-text-primary/20 duration-[1500ms] ease-luxury group-hover:bg-accent/40"
              style="height: {h}px;"
            ></div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Title -->
    <h3
      class="min-w-0 flex-1 truncate text-4xl font-serif leading-[0.9] text-text-primary duration-500 ease-luxury group-hover:text-accent"
    >
      {memo.title}
    </h3>

    <!-- Duration -->
    <span class="shrink-0 text-xs uppercase tracking-[0.2em] tabular-nums text-text-muted">
      {formatDuration(memo.duration_ms)}
    </span>

    <!-- Speakers -->
    {#if memo.speaker_count > 0}
      <span class="hidden shrink-0 text-xs uppercase tracking-[0.2em] text-text-muted sm:block">
        {memo.speaker_count} speaker{memo.speaker_count > 1 ? 's' : ''}
      </span>
    {/if}

    <!-- Last edited -->
    <span class="hidden shrink-0 text-xs uppercase tracking-[0.2em] text-text-muted md:block">
      {formatRelativeTime(memo.updated_at)}
    </span>

    <!-- Progress bar (list view) for active jobs -->
    {#if isActive}
      <div class="flex shrink-0 items-center gap-2">
        <div class="h-1 w-16 overflow-hidden bg-text-primary/10 rounded-none">
          {#if progressPct > 0 && progressPct < 20}
            <div class="relative h-full w-full">
              <div
                class="h-full bg-accent/60 transition-all duration-500 ease-luxury"
                style="width: {progressPct}%"
              ></div>
              <div
                class="absolute inset-0 h-full w-full animate-pulse bg-gradient-to-r from-accent/0 via-accent/40 to-accent/0"
              ></div>
            </div>
          {:else}
            <div
              class="h-full bg-accent transition-all duration-500 ease-luxury"
              style="width: {progressPct}%"
            ></div>
          {/if}
        </div>
        <span class="text-xs uppercase tracking-[0.2em] text-accent font-medium tabular-nums">
          {progressPct}%
        </span>
      </div>
    {:else}
    <!-- Status badge for completed/failed memos -->
      <div class="flex shrink-0 flex-col items-end gap-1">
        {#if isFailed && memo.error_message}
          <span class="text-xs text-error/70 line-clamp-1 max-w-[200px]" title={memo.error_message}
            >{memo.error_message}</span
          >
        {/if}
        <span
          class="shrink-0 rounded-none border border-text-primary/20 px-2 py-1 text-xs uppercase tracking-[0.2em] font-medium {getStatusColor(
            memo.status
          )}"
        >
          {getStatusLabel(memo.status)}
        </span>
      </div>
    {/if}

    <!-- Actions -->
    {#if isFailed}
      <div class="flex shrink-0 items-center gap-2">
        {#if memo.error_message}
          <span class="hidden text-xs text-error/70 line-clamp-1 max-w-[160px] sm:block" title={memo.error_message}
            >{memo.error_message}</span
          >
        {/if}
        <button
          onclick={handleRetry}
          disabled={retrying}
          class="shrink-0 rounded-none bg-transparent px-3 py-1.5 text-xs uppercase tracking-[0.2em] font-medium text-text-primary duration-500 ease-luxury hover:text-accent disabled:opacity-50"
          data-action="retry"
          aria-label="Retry transcription"
        >
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      </div>
    {/if}

    <button
      onclick={handleDeleteClick}
      class="shrink-0 rounded-none px-2 py-1 text-xs uppercase tracking-[0.2em] text-text-muted opacity-0 duration-500 ease-luxury group-hover:opacity-100 hover:text-error"
      data-action="delete"
      aria-label="Delete memo"
    >
      Delete
    </button>
  </div>
{/if}

<!-- Delete confirmation overlay -->
{#if showDeleteConfirm}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-surface-900/80 backdrop-blur-sm"
    onclick={(e) => {
      e.stopPropagation();
      cancelDelete();
    }}
    onkeydown={(e) => {
      if (e.key === 'Escape') cancelDelete();
    }}
  >
    <div
      class="mx-4 max-w-md rounded-none border-t border-text-primary/20 bg-surface-900 p-8 shadow-[0_8px_24px_rgba(0,0,0,0.06)]"
      onclick={(e) => e.stopPropagation()}
    >
      <h3 class="text-5xl font-serif leading-[0.9] text-text-primary">Delete Memo</h3>
      <p class="mt-6 text-sm text-text-secondary">
        Are you sure you want to delete "{memo.title}"? This action cannot be undone.
      </p>
      <div class="mt-8 flex justify-end gap-4">
        <button
          onclick={cancelDelete}
          class="rounded-none border-b border-text-primary bg-transparent px-6 py-2 text-xs uppercase tracking-[0.2em] text-text-primary duration-500 ease-luxury hover:border-accent hover:text-accent"
        >
          Cancel
        </button>
        <button
          onclick={confirmDelete}
          class="rounded-none border-b border-error bg-transparent px-6 py-2 text-xs uppercase tracking-[0.2em] font-medium text-error duration-500 ease-luxury hover:border-red-600 hover:text-red-600"
        >
          Delete
        </button>
      </div>
    </div>
  </div>
{/if}
