<script lang="ts">
  import { getToasts, dismissToast } from '$lib/stores/toasts.svelte';
  import type { ToastType } from '$lib/stores/toasts.svelte';

  const toasts = $derived(getToasts());

  const iconColor: Record<ToastType, string> = {
    error: 'text-error',
    warning: 'text-warning',
    info: 'text-blue-400',
    success: 'text-success'
  };

  const borderColor: Record<ToastType, string> = {
    error: 'border-error/30',
    warning: 'border-warning/30',
    info: 'border-blue-400/30',
    success: 'border-success/30'
  };

  function iconPath(type: ToastType): string {
    switch (type) {
      case 'error':
        return 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
      case 'warning':
        return 'M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z';
      case 'success':
        return 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z';
      case 'info':
        return 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
    }
  }
</script>

{#if toasts.length > 0}
  <div
    class="fixed bottom-6 right-6 z-50 flex flex-col gap-2"
    role="region"
    aria-label="Notifications"
  >
    {#each toasts as toast (toast.id)}
      <div
        class="flex items-start gap-3 rounded-xl border bg-surface-800 px-4 py-3 shadow-xl animate-slide-up {borderColor[
          toast.type
        ]}"
        role="alert"
      >
        <!-- Icon -->
        <svg
          class="mt-0.5 h-5 w-5 shrink-0 {iconColor[toast.type]}"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d={iconPath(toast.type)} />
        </svg>
        <p class="min-w-0 flex-1 text-sm text-text-primary">{toast.message}</p>
        {#if toast.dismissible}
          <button
            onclick={() => dismissToast(toast.id)}
            class="shrink-0 rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
            aria-label="Dismiss"
          >
            <svg
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  @keyframes slide-up {
    from {
      opacity: 0;
      transform: translateY(0.5rem);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .animate-slide-up {
    animation: slide-up 0.2s ease-out;
  }
</style>
