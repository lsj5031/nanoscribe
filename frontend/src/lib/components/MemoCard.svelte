<!--
  MemoCard: Displays a memo in either grid or list layout.
  Shows waveform thumbnail, title, duration, speaker count, last edited, status badge.
  Failed cards show a retry button.
  Clicking the card navigates to the editor.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
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
    class="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-surface-800 transition-colors hover:border-accent/40"
    role="link"
  >
    <!-- Waveform area -->
    <div class="relative h-20 w-full overflow-hidden bg-surface-700">
      {#if memo.waveform_url}
        <!-- svelte-ignore a11y_img_redundant_alt -->
        <img
          src={memo.waveform_url}
          alt="Waveform"
          class="h-full w-full object-cover opacity-60"
          loading="lazy"
        />
      {:else}
        <!-- Placeholder bars for memos without waveform -->
        <div class="flex h-full items-end justify-center gap-0.5 px-2 pb-2 pt-4">
          {#each Array(40) as _, i}
            {@const h = 8 + Math.sin(i * 0.5) * 12 + Math.cos(i * 0.3) * 8}
            <div class="flex-1 rounded-t bg-surface-500" style="height: {h}px;"></div>
          {/each}
        </div>
      {/if}

      <!-- Status badge -->
      <span
        class="absolute right-2 top-2 rounded-full px-2 py-0.5 text-xs font-medium {getStatusColor(
          memo.status
        )}"
      >
        {getStatusLabel(memo.status)}
      </span>

      <!-- Active indicator -->
      {#if isActive}
        <div class="absolute left-2 top-2">
          <div class="h-2 w-2 animate-pulse rounded-full bg-accent"></div>
        </div>
      {/if}
    </div>

    <!-- Content -->
    <div class="flex flex-1 flex-col gap-1.5 p-3">
      <h3 class="truncate text-sm font-medium text-text-primary">
        {memo.title}
      </h3>
      <div class="flex items-center gap-3 text-xs text-text-muted">
        <span>{formatDuration(memo.duration_ms)}</span>
        {#if memo.speaker_count > 0}
          <span>{memo.speaker_count} speaker{memo.speaker_count > 1 ? 's' : ''}</span>
        {/if}
      </div>
      <div class="mt-auto pt-1 text-xs text-text-muted">
        {formatRelativeTime(memo.updated_at)}
      </div>
    </div>

    <!-- Actions -->
    {#if isFailed}
      <div class="flex gap-1 border-t border-border px-3 py-2">
        <button
          onclick={handleRetry}
          disabled={retrying}
          class="flex-1 rounded-lg bg-accent/10 px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          data-action="retry"
          aria-label="Retry transcription"
        >
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
        <button
          onclick={handleDeleteClick}
          class="rounded-lg px-2 py-1 text-xs text-text-muted transition-colors hover:bg-surface-600 hover:text-error"
          data-action="delete"
          aria-label="Delete memo"
        >
          <svg
            class="h-3.5 w-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="3,6 5,6 21,6" />
            <path
              d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
            />
          </svg>
        </button>
      </div>
    {:else if memo.status === 'completed'}
      <div
        class="flex justify-end border-t border-border px-3 py-1.5 opacity-0 transition-opacity group-hover:opacity-100"
      >
        <button
          onclick={handleDeleteClick}
          class="rounded-lg p-1 text-text-muted transition-colors hover:bg-surface-600 hover:text-error"
          data-action="delete"
          aria-label="Delete memo"
        >
          <svg
            class="h-3.5 w-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="3,6 5,6 21,6" />
            <path
              d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
            />
          </svg>
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
    class="group flex cursor-pointer items-center gap-4 rounded-lg border border-border bg-surface-800 px-4 py-3 transition-colors hover:border-accent/40"
    role="link"
  >
    <!-- Waveform thumbnail -->
    <div class="h-8 w-20 shrink-0 overflow-hidden rounded bg-surface-700">
      {#if memo.waveform_url}
        <!-- svelte-ignore a11y_img_redundant_alt -->
        <img
          src={memo.waveform_url}
          alt="Waveform"
          class="h-full w-full object-cover opacity-60"
          loading="lazy"
        />
      {:else}
        <div class="flex h-full items-end justify-center gap-px px-1 pb-1 pt-2">
          {#each Array(20) as _, i}
            {@const h = 4 + Math.sin(i * 0.5) * 6}
            <div class="flex-1 rounded-t bg-surface-500" style="height: {h}px;"></div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Title -->
    <h3 class="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
      {memo.title}
    </h3>

    <!-- Duration -->
    <span class="shrink-0 text-xs tabular-nums text-text-muted">
      {formatDuration(memo.duration_ms)}
    </span>

    <!-- Speakers -->
    {#if memo.speaker_count > 0}
      <span class="hidden shrink-0 text-xs text-text-muted sm:block">
        {memo.speaker_count} speaker{memo.speaker_count > 1 ? 's' : ''}
      </span>
    {/if}

    <!-- Last edited -->
    <span class="hidden shrink-0 text-xs text-text-muted md:block">
      {formatRelativeTime(memo.updated_at)}
    </span>

    <!-- Status badge -->
    <span
      class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium {getStatusColor(memo.status)}"
    >
      {getStatusLabel(memo.status)}
    </span>

    <!-- Actions -->
    {#if isFailed}
      <button
        onclick={handleRetry}
        disabled={retrying}
        class="shrink-0 rounded-lg bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
        data-action="retry"
        aria-label="Retry transcription"
      >
        {retrying ? 'Retrying…' : 'Retry'}
      </button>
    {/if}

    <button
      onclick={handleDeleteClick}
      class="shrink-0 rounded-lg p-1 text-text-muted opacity-0 transition-opacity group-hover:opacity-100 hover:bg-surface-600 hover:text-error"
      data-action="delete"
      aria-label="Delete memo"
    >
      <svg
        class="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="3,6 5,6 21,6" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
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
      class="mx-4 max-w-sm rounded-xl border border-border bg-surface-800 p-6"
      onclick={(e) => e.stopPropagation()}
    >
      <h3 class="text-lg font-semibold text-text-primary">Delete Memo</h3>
      <p class="mt-2 text-sm text-text-secondary">
        Are you sure you want to delete "{memo.title}"? This action cannot be undone.
      </p>
      <div class="mt-4 flex justify-end gap-2">
        <button
          onclick={cancelDelete}
          class="rounded-lg border border-border bg-surface-700 px-4 py-2 text-sm text-text-primary transition-colors hover:bg-surface-600"
        >
          Cancel
        </button>
        <button
          onclick={confirmDelete}
          class="rounded-lg bg-error px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-error/80"
        >
          Delete
        </button>
      </div>
    </div>
  </div>
{/if}
