<script lang="ts">
  import '../app.css';
  import TopBar from '$lib/components/TopBar.svelte';
  import DropOverlay from '$lib/components/DropOverlay.svelte';
  import ProcessingOverlay from '$lib/components/ProcessingOverlay.svelte';
  import ErrorToast from '$lib/components/ErrorToast.svelte';
  import SearchOverlay from '$lib/components/SearchOverlay.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';
  import { openSearch, closeSearch, getOpen } from '$lib/stores/search.svelte';

  let { children } = $props();

  // Fetch capabilities on app load
  $effect(() => {
    getCapabilities();
  });

  function handleGlobalKeydown(e: KeyboardEvent) {
    const isOpen = getOpen();

    // Cmd/Ctrl+K opens search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (isOpen) {
        closeSearch();
      } else {
        openSearch();
      }
      return;
    }

    // Escape closes search (only when open)
    if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      closeSearch();
      return;
    }
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<div class="flex h-screen flex-col bg-surface-900">
  <TopBar />
  <main class="flex-1 overflow-y-auto">
    {@render children()}
  </main>
</div>

<!-- Global overlays -->
<DropOverlay />
<ProcessingOverlay />
<ErrorToast />
<SearchOverlay />
