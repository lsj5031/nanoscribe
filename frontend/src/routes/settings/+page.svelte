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

<div class="mx-auto max-w-2xl px-4 py-12">
  <h1 class="font-serif text-4xl leading-tight text-text-primary">Settings</h1>
  <p class="mt-4 text-sm font-sans text-text-secondary">
    Configure NanoScribe and view system status.
  </p>

  {#if isLoading}
    <div class="mt-12 flex justify-center">
      <div
        class="h-8 w-8 animate-spin rounded-none border border-text-primary/20 border-t-accent"
      ></div>
    </div>
  {:else}
    <div class="mt-12 space-y-12">
      <!-- System Status -->
      <section class="border-t border-text-primary/20 pt-8">
        <h2 class="font-serif text-2xl leading-tight text-text-primary">System Status</h2>
        <div class="mt-6 space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Status</span>
            <span class="flex items-center gap-2 text-xs uppercase tracking-[0.2em]">
              {#if status.status === 'ready'}
                <span class="h-2 w-2 rounded-none bg-success"></span>
                <span class="text-success">Ready</span>
              {:else if status.status === 'loading'}
                <span class="h-2 w-2 rounded-none bg-warning"></span>
                <span class="text-warning">Loading</span>
              {:else}
                <span class="h-2 w-2 rounded-none bg-error"></span>
                <span class="text-error">Error</span>
              {/if}
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Model</span>
            <span class="text-sm font-sans text-text-primary">{caps.asr_model || '—'}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Device</span>
            <span class="text-xs uppercase tracking-[0.2em] text-text-primary">{status.device}</span
            >
          </div>
          {#if status.gpu_available}
            <div class="flex items-center justify-between">
              <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">GPU</span>
              <span class="text-sm font-sans text-text-primary"
                >{status.gpu_name || 'Available'}</span
              >
            </div>
          {/if}
        </div>
      </section>

      <!-- Transcription Settings -->
      <section class="border-t border-text-primary/20 pt-8">
        <h2 class="font-serif text-2xl leading-tight text-text-primary">Transcription</h2>
        <div class="mt-6 space-y-8">
          {#if caps.speaker_diarization}
            <div class="flex items-center justify-between">
              <div>
                <span class="text-xs uppercase tracking-[0.2em] text-text-secondary"
                  >Speaker Diarization</span
                >
                <p class="mt-2 text-sm font-sans text-text-muted">
                  Identify and label different speakers
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={getDiarizationEnabled()}
                aria-label="Toggle speaker diarization"
                onclick={handleDiarizationToggle}
                class="relative inline-flex h-6 w-12 shrink-0 cursor-pointer rounded-none border border-text-primary/20 transition-colors duration-500 ease-luxury {getDiarizationEnabled()
                  ? 'bg-accent border-accent'
                  : 'bg-transparent'}"
              >
                <span
                  class="pointer-events-none inline-block h-5 w-5 transform rounded-none bg-text-primary shadow-none transition duration-500 ease-luxury {getDiarizationEnabled()
                    ? 'translate-x-6 bg-surface-900'
                    : 'translate-x-0'}"
                ></span>
              </button>
            </div>
          {/if}

          {#if caps.hotwords}
            <div>
              <label
                for="hotwords"
                class="block text-xs uppercase tracking-[0.2em] text-text-secondary">Hotwords</label
              >
              <p class="mb-4 mt-2 text-sm font-sans text-text-muted">
                Enter keywords to improve recognition, one per line
              </p>
              <textarea
                id="hotwords"
                rows="3"
                class="w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary placeholder-text-muted transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
                placeholder="e.g. NanoScribe&#10;FunASR"
                value={hotwordsInput}
                oninput={handleHotwordsInput}
                onblur={handleHotwordsBlur}
              ></textarea>
            </div>
          {/if}

          <div>
            <label
              for="language"
              class="block text-xs uppercase tracking-[0.2em] text-text-secondary">Language</label
            >
            <p class="mb-4 mt-2 text-sm font-sans text-text-muted">
              {caps.language_auto_detect
                ? 'Auto-detect is available — override only if needed'
                : 'Select the language for transcription'}
            </p>
            <select
              id="language"
              class="w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
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
      <section class="border-t border-text-primary/20 pt-8">
        <h2 class="font-serif text-2xl leading-tight text-text-primary">Storage</h2>
        <div class="mt-6 space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary"
              >Data Directory</span
            >
            <span class="text-sm font-sans text-text-primary">{status.data_dir}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Storage Used</span>
            <span class="text-sm font-sans text-text-primary">{status.storage_used_mb} MB</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Memos</span>
            <span class="text-sm font-sans text-text-primary">{status.memo_count}</span>
          </div>
          <div class="flex items-start justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Cached Models</span
            >
            <div class="flex flex-wrap items-center justify-end gap-2">
              {#each status.models_cached as model}
                <span
                  class="rounded-none border border-text-primary/20 px-2 py-1 text-xs uppercase tracking-[0.2em] text-text-secondary"
                >
                  {model}
                </span>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <!-- About -->
      <section class="border-t border-text-primary/20 pt-8">
        <h2 class="font-serif text-2xl leading-tight text-text-primary">About</h2>
        <div class="mt-6 space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">App</span>
            <span class="text-sm font-sans text-text-primary">NanoScribe v0.1.0</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-[0.2em] text-text-secondary">Engine</span>
            <a
              href="https://github.com/modelscope/FunASR"
              target="_blank"
              rel="noopener noreferrer"
              class="text-sm font-sans text-accent transition-colors duration-500 ease-luxury hover:text-text-primary"
            >
              FunASR
              <svg
                class="ml-1 inline h-3 w-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
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
