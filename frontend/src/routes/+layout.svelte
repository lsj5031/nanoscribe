<script lang="ts">
  import { onMount } from 'svelte';
  import '../app.css';
  import TopBar from '$lib/components/TopBar.svelte';
  import DropOverlay from '$lib/components/DropOverlay.svelte';
  import ProcessingOverlay from '$lib/components/ProcessingOverlay.svelte';
  import ErrorToast from '$lib/components/ErrorToast.svelte';
  import SearchOverlay from '$lib/components/SearchOverlay.svelte';
  import KeyboardShortcuts from '$lib/components/KeyboardShortcuts.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';
  import { openSearch, closeSearch, getOpen } from '$lib/stores/search.svelte';
  import { showError } from '$lib/stores/toasts.svelte';
  import { pwaInfo } from 'virtual:pwa-info';

  let { children } = $props();

  const webManifest = $derived(pwaInfo ? pwaInfo.webManifest.linkTag : '');

  // Fetch capabilities on app load
  $effect(() => {
    getCapabilities();
  });

  // Register PWA service worker
  onMount(async () => {
    if (pwaInfo) {
      const { registerSW } = await import('virtual:pwa-register');
      registerSW({
        immediate: true,
        onRegistered(r) {
          console.log(`SW Registered: ${r?.scope}`);
        },
        onRegisterError(error) {
          console.log('SW registration error', error);
        }
      });
    }
  });

  // Global unhandled error handlers
  $effect(() => {
    function handleUnhandledRejection(e: PromiseRejectionEvent) {
      // Prevent default browser console error
      e.preventDefault();

      const reason = e.reason;

      // Network errors (fetch failures, no connectivity)
      if (reason instanceof TypeError && reason.message === 'Failed to fetch') {
        showError('Network error — please check your connection');
        return;
      }

      // Response errors with status codes
      if (reason?.status && reason?.statusText) {
        showError(`Request failed (${reason.status}): ${reason.statusText}`);
        return;
      }

      // Generic Error objects
      if (reason instanceof Error) {
        // Avoid showing duplicate toasts for errors already handled by stores
        if (reason.message.includes('Failed to fetch memo')) return;
        if (reason.message.includes('Failed to load')) return;
        showError(reason.message);
        return;
      }

      // Unknown rejection
      if (reason && typeof reason === 'string') {
        showError(reason);
      }
    }

    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    return () => window.removeEventListener('unhandledrejection', handleUnhandledRejection);
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

<svelte:head>
  {@html webManifest}
</svelte:head>

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
<KeyboardShortcuts />
