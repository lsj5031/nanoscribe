<script lang="ts">
  import { getCapabilities, getCapabilitiesLoading } from '$lib/stores/capabilities.svelte';
  import {
    getSystemStatus,
    getSystemStatusLoading,
    fetchSystemStatus
  } from '$lib/stores/system-status.svelte';
  import {
    getDiarizationEnabled,
    setDiarizationEnabled,
    getHotwords,
    setHotwords,
    getLanguage,
    setLanguage,
    LANGUAGES,
    type LanguageOption
  } from '$lib/stores/settings.svelte';

  let hotwordsInput = $state(getHotwords());
  let hotwordsDirty = $state(false);

  const caps = $derived(getCapabilities());
  const status = $derived(getSystemStatus());
  const isLoading = $derived(getCapabilitiesLoading() || getSystemStatusLoading());

  function handleHotwordsInput(e: Event) {
    const target = e.target as HTMLTextAreaElement;
    hotwordsInput = target.value;
    hotwordsDirty = true;
  }

  function handleHotwordsBlur() {
    if (hotwordsDirty) {
      setHotwords(hotwordsInput);
      hotwordsDirty = false;
    }
  }

  function handleLanguageChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    setLanguage(target.value as LanguageOption);
  }

  function handleDiarizationToggle() {
    setDiarizationEnabled(!getDiarizationEnabled());
  }
</script>

<div class="mx-auto max-w-2xl px-4 py-8">
  <h1 class="text-2xl font-semibold text-text-primary">Settings</h1>
  <p class="mt-1 text-sm text-text-secondary">Configure NanoScribe and view system status.</p>

  {#if isLoading}
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
              {#if status.status === 'ready'}
                <span class="h-2 w-2 rounded-full bg-success"></span>
                <span class="text-success">Ready</span>
              {:else if status.status === 'loading'}
                <span class="h-2 w-2 rounded-full bg-warning"></span>
                <span class="text-warning">Loading</span>
              {:else}
                <span class="h-2 w-2 rounded-full bg-error"></span>
                <span class="text-error">Error</span>
              {/if}
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Model</span>
            <span class="text-sm font-mono text-text-primary">{caps.asr_model || '—'}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Device</span>
            <span class="text-sm text-text-primary uppercase">{status.device}</span>
          </div>
          {#if status.gpu_available}
            <div class="flex items-center justify-between">
              <span class="text-sm text-text-secondary">GPU</span>
              <span class="text-sm text-text-primary">{status.gpu_name || 'Available'}</span>
            </div>
          {/if}
        </div>
      </section>

      <!-- Transcription Settings -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">Transcription</h2>
        <div class="mt-4 space-y-4">
          {#if caps.speaker_diarization}
            <div class="flex items-center justify-between">
              <div>
                <span class="text-sm text-text-secondary">Speaker Diarization</span>
                <p class="text-xs text-text-muted">Identify and label different speakers</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={getDiarizationEnabled()}
                aria-label="Toggle speaker diarization"
                onclick={handleDiarizationToggle}
                class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out {getDiarizationEnabled()
                  ? 'bg-accent'
                  : 'bg-surface-600'}"
              >
                <span
                  class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out {getDiarizationEnabled()
                    ? 'translate-x-5'
                    : 'translate-x-0'}"
                ></span>
              </button>
            </div>
          {/if}

          {#if caps.hotwords}
            <div>
              <label for="hotwords" class="text-sm text-text-secondary">Hotwords</label>
              <p class="mb-1.5 text-xs text-text-muted">
                Enter keywords to improve recognition, one per line
              </p>
              <textarea
                id="hotwords"
                rows="3"
                class="w-full rounded-lg border border-border bg-surface-700 px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                placeholder="e.g. NanoScribe&#10;FunASR"
                value={hotwordsInput}
                oninput={handleHotwordsInput}
                onblur={handleHotwordsBlur}
              ></textarea>
            </div>
          {/if}

          <div>
            <label for="language" class="text-sm text-text-secondary">Language</label>
            <p class="mb-1.5 text-xs text-text-muted">
              {caps.language_auto_detect
                ? 'Auto-detect is available — override only if needed'
                : 'Select the language for transcription'}
            </p>
            <select
              id="language"
              class="w-full rounded-lg border border-border bg-surface-700 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
              value={getLanguage()}
              onchange={handleLanguageChange}
            >
              {#each LANGUAGES as lang}
                <option value={lang.value}>{lang.label}</option>
              {/each}
            </select>
          </div>
        </div>
      </section>

      <!-- Storage -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">Storage</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Data Directory</span>
            <span class="text-sm font-mono text-text-primary">{status.data_dir}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Storage Used</span>
            <span class="text-sm text-text-primary">{status.storage_used_mb} MB</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Memos</span>
            <span class="text-sm text-text-primary">{status.memo_count}</span>
          </div>
          <div class="flex items-start justify-between">
            <span class="text-sm text-text-secondary">Cached Models</span>
            <div class="flex flex-wrap justify-end gap-1.5">
              {#each status.models_cached as model}
                <span
                  class="rounded-full bg-surface-600 px-2 py-0.5 text-xs font-mono text-text-secondary"
                >
                  {model}
                </span>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <!-- About -->
      <section class="rounded-xl border border-border bg-surface-800 p-6">
        <h2 class="text-lg font-medium text-text-primary">About</h2>
        <div class="mt-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">App</span>
            <span class="text-sm text-text-primary">NanoScribe v0.1.0</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text-secondary">Engine</span>
            <a
              href="https://github.com/modelscope/FunASR"
              target="_blank"
              rel="noopener noreferrer"
              class="text-sm text-accent hover:underline"
            >
              FunASR
              <svg
                class="ml-0.5 inline h-3 w-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </div>
        </div>
      </section>
    </div>
  {/if}
</div>
