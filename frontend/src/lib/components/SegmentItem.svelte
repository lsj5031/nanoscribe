<script lang="ts">
  import type { Segment } from '$lib/stores/editor.svelte';
  import {
    formatTime,
    getSpeakerColor,
    getSpeakerDisplayName,
    renameSpeaker,
    getEditingSegmentId,
    getSaving,
    getSaveError,
    updateSegmentText,
    setEditingSegmentId
  } from '$lib/stores/editor.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';

  let {
    segment,
    isCurrent = false,
    isHovered = false,
    searchQuery = '',
    onclick
  }: {
    segment: Segment;
    isCurrent: boolean;
    isHovered?: boolean;
    searchQuery?: string;
    onclick: () => void;
  } = $props();

  const timeDisplay = $derived(formatTime(segment.start_ms));
  const speakerColor = $derived(getSpeakerColor(segment.speaker_key));
  const speakerDisplayName = $derived(getSpeakerDisplayName(segment.speaker_key));
  const showSpeakerBadge = $derived(getCapabilities().speaker_diarization && segment.speaker_key);
  const editingSegmentId = $derived(getEditingSegmentId());
  const saving = $derived(getSaving());
  const saveError = $derived(getSaveError());
  const isEditing = $derived(editingSegmentId === segment.id);

  let textarea: HTMLTextAreaElement | undefined = $state();
  let localText: string = $state('');
  let showSaved: boolean = $state(false);

  let isRenaming: boolean = $state(false);
  let renameInput: HTMLInputElement | undefined = $state();
  let renameText: string = $state('');

  $effect(() => {
    localText = segment.text;
  });

  $effect(() => {
    if (isEditing && textarea) {
      textarea.focus();
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

  const textParts = $derived.by(() => {
    if (!searchQuery || isEditing) {
      return [{ text: segment.text, highlight: false }];
    }
    const lower = segment.text.toLowerCase();
    const parts: { text: string; highlight: boolean }[] = [];
    let lastIdx = 0;
    let pos = 0;
    while (pos < lower.length) {
      const idx = lower.indexOf(searchQuery, pos);
      if (idx === -1) break;
      if (idx > lastIdx) {
        parts.push({ text: segment.text.slice(lastIdx, idx), highlight: false });
      }
      parts.push({ text: segment.text.slice(idx, idx + searchQuery.length), highlight: true });
      lastIdx = idx + searchQuery.length;
      pos = lastIdx;
    }
    if (lastIdx < segment.text.length) {
      parts.push({ text: segment.text.slice(lastIdx), highlight: false });
    }
    return parts;
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  class="w-full cursor-pointer border-l-2 px-12 py-8 text-left transition-all duration-500 ease-luxury {isCurrent
    ? 'border-[#D4AF37] bg-[#1A1A1A]/5'
    : isHovered
      ? 'border-[#1A1A1A]/10 bg-transparent'
      : 'border-transparent hover:border-[#1A1A1A]/10 hover:bg-transparent'}"
  role="option"
  aria-selected={isCurrent}
  tabindex="-1"
  onclick={handleRowClick}
>
  <div class="flex items-start gap-8">
    <!-- Timestamp -->
    <span
      class="shrink-0 font-sans text-xs uppercase tracking-[0.2em] mt-1.5 {isCurrent
        ? 'text-[#D4AF37]'
        : 'text-[#1A1A1A]/40'}"
    >
      {timeDisplay}
    </span>

    <div class="min-w-0 flex-1">
      <!-- Speaker badge + save indicator -->
      <div class="mb-4 flex items-center gap-4">
        {#if showSpeakerBadge}
          {#if isRenaming}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="flex items-center gap-3" onclick={(e) => e.stopPropagation()}>
              <span
                class="inline-block h-3 w-3 shrink-0 rounded-none border border-[#1A1A1A]/20"
                style="background-color: {speakerColor}"
              ></span>
              <input
                bind:this={renameInput}
                bind:value={renameText}
                onkeydown={handleRenameKeydown}
                onblur={handleRenameBlur}
                class="w-32 border-b border-[#1A1A1A]/20 bg-transparent px-0 py-1 text-xs uppercase tracking-[0.2em] text-[#1A1A1A] outline-none transition-colors duration-500 ease-luxury focus:border-[#D4AF37] rounded-none"
                maxlength="50"
              />
            </div>
          {:else}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="flex cursor-pointer items-center gap-3 transition-opacity duration-500 ease-luxury hover:opacity-70"
              onclick={handleBadgeClick}
              role="button"
              tabindex="-1"
              title="Click to rename speaker"
            >
              <span
                class="inline-block h-3 w-3 shrink-0 rounded-none border border-[#1A1A1A]/20"
                style="background-color: {speakerColor}"
              ></span>
              <span class="text-xs uppercase tracking-[0.2em] text-[#1A1A1A]"
                >{speakerDisplayName}</span
              >
            </div>
          {/if}
        {/if}
        {#if segment.edited && !isEditing}
          <span class="text-[10px] uppercase tracking-[0.2em] text-[#1A1A1A]/40" title="Edited">
            Edited
          </span>
        {/if}
        {#if isEditing && saving}
          <span class="text-[10px] uppercase tracking-[0.2em] text-[#1A1A1A]/40">Saving...</span>
        {/if}
        {#if showSaved}
          <span class="text-[10px] uppercase tracking-[0.2em] text-[#D4AF37]">Saved</span>
        {/if}
        {#if saveError}
          <span class="text-[10px] uppercase tracking-[0.2em] text-[#1A1A1A]" title={saveError}>
            Error
          </span>
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
          class="w-full resize-none border-b border-[#D4AF37] bg-transparent py-2 font-sans text-lg leading-loose text-[#1A1A1A] outline-none shadow-[0_2px_8px_rgba(0,0,0,0.02)] rounded-none"
          rows="1"
        ></textarea>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <p
          class="cursor-text font-sans text-lg leading-loose {isCurrent
            ? 'text-[#1A1A1A]'
            : 'text-[#1A1A1A]/80'}"
          onclick={handleTextClick}
        >
          {#each textParts as part}
            {#if part.highlight}
              <mark class="bg-[#D4AF37]/20 text-inherit px-1 rounded-none">{part.text}</mark>
            {:else}
              {part.text}
            {/if}
          {/each}
        </p>
      {/if}
    </div>
  </div>
</div>
