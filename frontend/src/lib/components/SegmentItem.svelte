<script lang="ts">
  import type { Segment } from '$lib/stores/editor.svelte';
  import {
    formatTime,
    getSpeakerColor,
    getSpeakerDisplayName,
    renameSpeaker,
    getEditingSegmentId,
    getSaving,
    updateSegmentText,
    setEditingSegmentId
  } from '$lib/stores/editor.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';

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
  const speakerDisplayName = $derived(getSpeakerDisplayName(segment.speaker_key));
  const showSpeakerBadge = $derived(getCapabilities().speaker_diarization && segment.speaker_key);
  const editingSegmentId = $derived(getEditingSegmentId());
  const saving = $derived(getSaving());
  const isEditing = $derived(editingSegmentId === segment.id);

  let textarea: HTMLTextAreaElement | undefined = $state();
  let localText: string = $state('');
  let showSaved: boolean = $state(false);

  // Speaker rename state
  let isRenaming: boolean = $state(false);
  let renameInput: HTMLInputElement | undefined = $state();
  let renameText: string = $state('');

  $effect(() => {
    // Sync local text when segment text changes externally (e.g., conflict refresh)
    localText = segment.text;
  });

  $effect(() => {
    if (isEditing && textarea) {
      textarea.focus();
      // Auto-resize textarea
      _resizeTextarea();
    }
  });

  $effect(() => {
    if (isRenaming && renameInput) {
      renameInput.focus();
      renameInput.select();
    }
  });

  function _resizeTextarea() {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  function handleTextClick(e: MouseEvent) {
    e.stopPropagation();
    if (!isEditing) {
      localText = segment.text;
      setEditingSegmentId(segment.id);
    }
  }

  function handleInput() {
    _resizeTextarea();
    if (localText !== segment.text) {
      updateSegmentText(segment.id, localText);
      showSaved = false;
    }
  }

  function handleBlur() {
    // Show saved indicator briefly
    if (segment.edited) {
      showSaved = true;
      setTimeout(() => {
        showSaved = false;
      }, 1500);
    }
    setEditingSegmentId(null);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      textarea?.blur();
    }
    // Prevent Space from propagating to global handler
    if (e.key === ' ') {
      e.stopPropagation();
    }
  }

  function handleRowClick() {
    if (!isEditing) {
      onclick();
    }
  }

  function handleBadgeClick(e: MouseEvent) {
    e.stopPropagation();
    if (!isRenaming && segment.speaker_key) {
      renameText = speakerDisplayName;
      isRenaming = true;
    }
  }

  function handleRenameKeydown(e: KeyboardEvent) {
    e.stopPropagation();
    if (e.key === 'Enter') {
      _saveRename();
    } else if (e.key === 'Escape') {
      isRenaming = false;
    }
  }

  function handleRenameBlur() {
    _saveRename();
  }

  async function _saveRename() {
    if (!isRenaming || !segment.speaker_key) return;
    const newName = renameText.trim();
    isRenaming = false;
    if (newName && newName !== speakerDisplayName) {
      try {
        await renameSpeaker(segment.speaker_key, newName);
      } catch {
        // Error handled in store
      }
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  class="w-full cursor-pointer border-l-2 px-4 py-2.5 text-left transition-colors {isCurrent
    ? 'border-accent bg-accent/5'
    : 'border-transparent hover:bg-surface-700'}"
  role="option"
  aria-selected={isCurrent}
  tabindex="-1"
  onclick={handleRowClick}
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
      <!-- Speaker badge + save indicator -->
      <div class="mb-1 flex items-center gap-1.5">
        {#if showSpeakerBadge}
          {#if isRenaming}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="flex items-center gap-1" onclick={(e) => e.stopPropagation()}>
              <span
                class="inline-block h-2 w-2 shrink-0 rounded-full"
                style="background-color: {speakerColor}"
              ></span>
              <input
                bind:this={renameInput}
                bind:value={renameText}
                onkeydown={handleRenameKeydown}
                onblur={handleRenameBlur}
                class="w-24 rounded border border-accent/40 bg-surface-900/50 px-1.5 py-0 text-xs text-text-primary outline-none focus:border-accent"
                maxlength="50"
              />
            </div>
          {:else}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="flex cursor-pointer items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-surface-600"
              onclick={handleBadgeClick}
              role="button"
              tabindex="-1"
              title="Click to rename speaker"
            >
              <span
                class="inline-block h-2 w-2 shrink-0 rounded-full"
                style="background-color: {speakerColor}"
              ></span>
              <span class="text-xs font-medium text-text-secondary">{speakerDisplayName}</span>
            </div>
          {/if}
        {/if}
        {#if segment.edited && !isEditing}
          <span class="text-[10px] text-text-muted" title="Edited">
            <svg
              class="inline h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
          </span>
        {/if}
        {#if isEditing && saving}
          <span class="text-[10px] text-text-muted">Saving...</span>
        {/if}
        {#if showSaved}
          <span class="text-[10px] text-accent">Saved</span>
        {/if}
      </div>

      <!-- Text -->
      {#if isEditing}
        <textarea
          bind:this={textarea}
          bind:value={localText}
          oninput={handleInput}
          onblur={handleBlur}
          onkeydown={handleKeydown}
          class="w-full resize-none border border-accent/30 bg-surface-900/50 px-2 py-1 text-sm leading-relaxed text-text-primary outline-none focus:border-accent"
          rows="1"
        ></textarea>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <p
          class="cursor-text text-sm leading-relaxed {isCurrent
            ? 'text-text-primary'
            : 'text-text-secondary'}"
          onclick={handleTextClick}
        >
          {segment.text || '...'}
        </p>
      {/if}
    </div>
  </div>
</div>
