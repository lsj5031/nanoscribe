<script lang="ts">
  import { getUploadError, clearUploadError } from '$lib/stores/upload.svelte';

  const error = $derived(getUploadError());

  let visible = $state(false);
  let timeout: ReturnType<typeof setTimeout> | null = null;

  $effect(() => {
    if (error) {
      visible = true;
      // Auto-dismiss after 6 seconds
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        visible = false;
        clearUploadError();
      }, 6000);
    } else {
      visible = false;
    }
  });

  function dismiss() {
    visible = false;
    if (timeout) clearTimeout(timeout);
    clearUploadError();
  }
</script>

{#if visible && error}
  <div class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-slide-up" role="alert">
    <div
      class="flex items-center gap-3 rounded-xl border border-error/30 bg-surface-800 px-5 py-3 shadow-xl"
    >
      <!-- Error icon -->
      <svg
        class="h-5 w-5 shrink-0 text-error"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
      <p class="text-sm text-text-primary">{error}</p>
      <button
        onclick={dismiss}
        class="ml-2 shrink-0 rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
        aria-label="Dismiss error"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
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
