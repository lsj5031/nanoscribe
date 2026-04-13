<script lang="ts">
  import { getCapabilities, getCapabilitiesLoading } from '$lib/stores/capabilities.svelte';
</script>

<div class="mx-auto max-w-2xl px-4 py-8">
  <h1 class="text-2xl font-semibold text-text-primary">Settings</h1>
  <p class="mt-1 text-sm text-text-secondary">Configure NanoScribe and view system status.</p>

  {#if getCapabilitiesLoading()}
    <div class="mt-8 flex justify-center">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent"></div>
    </div>
  {:else}
    <div class="mt-8 space-y-6">
      <!-- System Status -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">System Status</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Status</span>
            <span class="flex items-center gap-1.5 text-sm">
              {#if getCapabilities().ready}
                <span class="h-2 w-2 rounded-full bg-success"></span>
                <span class="text-success">Ready</span>
              {:else}
                <span class="h-2 w-2 rounded-full bg-warning"></span>
                <span class="text-warning">Not Ready</span>
              {/if}
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">GPU</span>
            <span class="flex items-center gap-1.5 text-sm">
              {#if getCapabilities().gpu}
                <span class="h-2 w-2 rounded-full bg-success"></span>
                <span class="text-success">Available</span>
              {:else}
                <span class="h-2 w-2 rounded-full bg-warning"></span>
                <span class="text-warning">Not Available</span>
              {/if}
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Device</span>
            <span class="text-sm text-text-primary">{getCapabilities().device}</span>
          </div>
        </div>
      </section>

      <!-- Models -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">Models</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">ASR Model</span>
            <span class="text-sm text-text-primary font-mono"
              >{getCapabilities().asr_model || '—'}</span
            >
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">VAD Model</span>
            <span class="text-sm text-text-primary font-mono">{getCapabilities().vad || '—'}</span>
          </div>
        </div>
      </section>

      <!-- Capabilities -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">Capabilities</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Timestamps</span>
            <span class="text-sm text-text-primary"
              >{getCapabilities().timestamps ? 'Yes' : 'No'}</span
            >
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Speaker Diarization</span>
            <span class="text-sm text-text-primary"
              >{getCapabilities().speaker_diarization ? 'Yes' : 'No'}</span
            >
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Hotwords</span>
            <span class="text-sm text-text-primary"
              >{getCapabilities().hotwords ? 'Yes' : 'No'}</span
            >
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Language Auto-Detect</span>
            <span class="text-sm text-text-primary"
              >{getCapabilities().language_auto_detect ? 'Yes' : 'No'}</span
            >
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Recording</span>
            <span class="text-sm text-text-primary"
              >{getCapabilities().recording ? 'Yes' : 'No'}</span
            >
          </div>
        </div>
      </section>

      <!-- Storage -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">Storage</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Data Directory</span>
            <span class="text-sm font-mono text-text-primary">/app/data</span>
          </div>
        </div>
      </section>
    </div>
  {/if}
</div>
