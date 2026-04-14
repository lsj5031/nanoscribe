<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { getOpen } from '$lib/stores/search.svelte';

  let toastMessage = $state('');
  let toastVisible = $state(false);
  let toastTimeout: ReturnType<typeof setTimeout> | null = null;

  function showToast(message: string) {
    toastMessage = message;
    toastVisible = true;
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toastVisible = false;
    }, 2000);
  }

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

    // Cmd/Ctrl+F: In-editor search placeholder (only in editor pages)
    if (mod && e.key === 'f') {
      const currentPath = $page.url.pathname;
      if (currentPath.startsWith('/memos/')) {
        e.preventDefault();
        showToast('In-editor search coming soon');
        return;
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if toastVisible}
  <div class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-slide-up" role="status">
    <div
      class="flex items-center gap-3 rounded-xl border border-accent/30 bg-surface-800 px-5 py-3 shadow-xl"
    >
      <p class="text-sm text-text-primary">{toastMessage}</p>
    </div>
  </div>
{/if}

<style>
  @keyframes slide-up {
    from {
      opacity: 0;
      transform: translate(-50%, 1rem);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }
  .animate-slide-up {
    animation: slide-up 0.2s ease-out;
  }
</style>
