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
<div class="fixed inset-0 z-50 bg-transparent" onclick={onclose}>
  <div
    class="absolute right-0 top-full mt-2 min-w-[200px] rounded-none border border-text-primary/20 bg-surface-800 p-2 shadow-[0_2px_8px_rgba(0,0,0,0.02)]"
  >
    <div class="mb-2 px-3 pb-2 pt-1 border-b border-text-primary/20">
      <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Export Format</span>
    </div>
    {#each formats as fmt}
      <button
        onclick={() => handleExport(fmt.value)}
        class="flex w-full items-center gap-4 rounded-none px-3 py-2 text-sm font-sans text-text-primary transition-colors duration-500 ease-luxury hover:bg-surface-700"
      >
        <span class="flex-1 text-left">{fmt.label}</span>
        <span class="text-[10px] uppercase tracking-[0.2em] text-text-muted">{fmt.ext}</span>
      </button>
    {/each}
  </div>
</div>
