<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { getOpen } from '$lib/stores/search.svelte';
  import { toggleTranscriptSearch } from '$lib/stores/editor.svelte';

  function handleKeydown(e: KeyboardEvent) {
    const mod = e.metaKey || e.ctrlKey;

    // Cmd/Ctrl+1: Navigate to library
    if (mod && e.key === '1') {
      e.preventDefault();
      goto('/');
      return;
    }

    // Cmd/Ctrl+2: Navigate to settings
    if (mod && e.key === '2') {
      e.preventDefault();
      goto('/settings');
      return;
    }

    // Cmd/Ctrl+F: In-editor transcript search (only in editor pages)
    if (mod && e.key === 'f') {
      const currentPath = $page.url.pathname;
      if (currentPath.startsWith('/memos/')) {
        e.preventDefault();
        toggleTranscriptSearch();
        return;
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />
