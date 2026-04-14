<script lang="ts">
  let {
    memoId,
    onclose
  }: {
    memoId: string;
    onclose: () => void;
  } = $props();

  const formats = [
    { value: 'txt', label: 'Plain Text', ext: '.txt' },
    { value: 'json', label: 'JSON', ext: '.json' },
    { value: 'srt', label: 'Subtitles (.srt)', ext: '.srt' }
  ];

  function handleExport(format: string) {
    window.open(`/api/memos/${memoId}/export?format=${format}`, '_blank');
    onclose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      onclose();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 z-50" onclick={onclose}>
  <div
    class="absolute right-0 top-full mt-1 min-w-[160px] rounded-lg border border-border bg-surface-800 py-1 shadow-xl"
  >
    {#each formats as fmt}
      <button
        onclick={() => handleExport(fmt.value)}
        class="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-700"
      >
        <span class="flex-1 text-left">{fmt.label}</span>
        <span class="text-xs text-text-muted">{fmt.ext}</span>
      </button>
    {/each}
  </div>
</div>
