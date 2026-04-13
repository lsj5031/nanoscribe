<script lang="ts">
  import { getCapabilities, getCapabilitiesLoading } from '$lib/stores/capabilities.svelte';
</script>

<div class="flex h-full flex-col items-center justify-center px-4">
  {#if getCapabilitiesLoading()}
    <!-- Loading state -->
    <div class="flex flex-col items-center gap-4">
      <div class="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent"></div>
      <p class="text-text-secondary">Loading…</p>
    </div>
  {:else if !getCapabilities().ready}
    <!-- Readiness card: models not ready -->
    <div
      class="flex max-w-md flex-col items-center gap-6 rounded-2xl border border-border bg-surface-800 p-8 text-center"
    >
      <div class="rounded-full bg-accent-muted p-4">
        <svg
          class="h-8 w-8 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83"
          />
        </svg>
      </div>
      <div>
        <h2 class="text-xl font-semibold text-text-primary">Setting Up</h2>
        <p class="mt-2 text-sm text-text-secondary">
          NanoScribe is preparing the transcription engine. This may take a few minutes on first run
          while models are downloaded.
        </p>
      </div>
      <div class="flex items-center gap-2 text-xs text-text-muted">
        <div class="h-2 w-2 animate-pulse rounded-full bg-accent"></div>
        <span>Checking model status…</span>
      </div>
    </div>
  {:else}
    <!-- Empty state: ready but no memos -->
    <div class="flex max-w-lg flex-col items-center gap-8">
      <!-- Animated waveform icon -->
      <div class="flex items-end gap-1">
        {#each [1, 2, 3, 4, 5, 6, 7] as bar}
          <div
            class="w-1.5 rounded-full bg-accent"
            style="height: {12 + Math.sin(bar * 0.8) * 16}px; animation: pulse 2s ease-in-out {bar *
              0.1}s infinite alternate;"
          ></div>
        {/each}
      </div>

      <div class="text-center">
        <h1 class="text-2xl font-semibold text-text-primary">No Memos Yet</h1>
        <p class="mt-2 text-text-secondary">
          Upload an audio file or record a new memo to get started with transcription.
        </p>
      </div>

      <!-- Upload area placeholder -->
      <div
        class="flex w-full max-w-sm flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border p-8 transition-colors hover:border-accent"
      >
        <svg
          class="h-10 w-10 text-text-muted"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17,8 12,3 7,8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <p class="text-sm text-text-muted">Drop audio files here or click to upload</p>
        <p class="text-xs text-text-muted">Supported: WAV, MP3, M4A, AAC, WebM, OGG, OPUS</p>
      </div>

      {#if getCapabilities().recording}
        <p class="text-xs text-text-muted">or record from microphone</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  @keyframes pulse {
    from {
      opacity: 0.4;
    }
    to {
      opacity: 1;
    }
  }
</style>
