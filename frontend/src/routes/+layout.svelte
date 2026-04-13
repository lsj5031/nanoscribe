<script lang="ts">
  import '../app.css';
  import TopBar from '$lib/components/TopBar.svelte';
  import { getCapabilities } from '$lib/stores/capabilities.svelte';

  let { children } = $props();

  // Fetch capabilities on app load
  $effect(() => {
    getCapabilities();
  });
</script>

<div class="flex h-screen flex-col bg-surface-900">
  <TopBar />
  <main class="flex-1 overflow-y-auto">
    {@render children()}
  </main>
</div>
