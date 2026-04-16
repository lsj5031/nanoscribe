<script lang="ts">
  import {
    getCapabilities,
    getCapabilitiesLoading,
    getEngineSettings,
    getEngineLoading,
    getEngineSaving,
    saveEngineSettings,
    type EngineSettings
  } from '$lib/stores/capabilities.svelte';
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
  import { showError, showSuccess } from '$lib/stores/toasts.svelte';

  let hotwordsInput = $state(getHotwords());
  let hotwordsDirty = $state(false);

  // Local editable copy of engine settings (synced on save)
  let localEngine = $state<EngineSettings>({ ...getEngineSettings() });
  let engineDirty = $state(false);

  const caps = $derived(getCapabilities());
  const status = $derived(getSystemStatus());
  const isLoading = $derived(
    getCapabilitiesLoading() || getSystemStatusLoading() || getEngineLoading()
  );
  const engineSaving = $derived(getEngineSaving());

  // Sync local engine state when remote settings load/change
  $effect(() => {
    const remote = getEngineSettings();
    if (!engineDirty) {
      localEngine = { ...remote };
    }
  });

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

  function handleEngineChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    localEngine.engine = target.value as 'local' | 'remote';
    engineDirty = true;
  }

  function handleRemoteUrlInput(e: Event) {
    localEngine.remote_url = (e.target as HTMLInputElement).value;
    engineDirty = true;
  }

  function handleRemoteModelInput(e: Event) {
    localEngine.remote_model = (e.target as HTMLInputElement).value;
    engineDirty = true;
  }

  function handleRemoteApiKeyInput(e: Event) {
    localEngine.remote_api_key = (e.target as HTMLInputElement).value;
    engineDirty = true;
  }

  function handleRemoteTimeoutInput(e: Event) {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (!isNaN(value) && value > 0) {
      localEngine.remote_timeout = value;
      engineDirty = true;
    }
  }

  async function handleSaveEngine() {
    const result = await saveEngineSettings(localEngine);
    if (result) {
      engineDirty = false;
      localEngine = { ...result };
      showSuccess(
        localEngine.engine === 'remote' ? 'Switched to remote engine' : 'Switched to local engine'
      );
      // Refresh status since device/capabilities changed
      fetchSystemStatus();
    } else {
      showError('Failed to save engine settings');
    }
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

      <!-- Engine Configuration -->
      <section class="border-t border-text-primary/20 pt-8">
        <h2 class="font-serif text-2xl leading-tight text-text-primary">Engine</h2>
        <p class="mt-2 text-sm font-sans text-text-muted">
          Choose between local GPU inference and a remote API.
        </p>
        <div class="mt-6 space-y-6">
          <div>
            <label for="engine" class="block text-xs uppercase tracking-[0.2em] text-text-secondary"
              >Transcription Engine</label
            >
            <select
              id="engine"
              class="mt-2 w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
              value={localEngine.engine}
              onchange={handleEngineChange}
            >
              <option value="local">Local (FunASR — requires GPU/CPU)</option>
              <option value="remote">Remote (OpenAI-compatible API)</option>
            </select>
          </div>

          {#if localEngine.engine === 'remote'}
            <div class="space-y-5 pl-2 border-l-2 border-accent/30">
              <div>
                <label
                  for="remote-url"
                  class="block text-xs uppercase tracking-[0.2em] text-text-secondary"
                  >Endpoint URL</label
                >
                <p class="mt-1 text-xs font-sans text-text-muted">
                  Include the <code class="text-accent">/v1</code> prefix, e.g. https://api.openai.com/v1
                </p>
                <input
                  id="remote-url"
                  type="url"
                  placeholder="https://api.openai.com/v1"
                  class="mt-2 w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary placeholder-text-muted transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
                  value={localEngine.remote_url}
                  oninput={handleRemoteUrlInput}
                />
              </div>

              <div>
                <label
                  for="remote-model"
                  class="block text-xs uppercase tracking-[0.2em] text-text-secondary"
                  >Model ID</label
                >
                <input
                  id="remote-model"
                  type="text"
                  placeholder="whisper-1"
                  class="mt-2 w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary placeholder-text-muted transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
                  value={localEngine.remote_model}
                  oninput={handleRemoteModelInput}
                />
              </div>

              <div>
                <label
                  for="remote-api-key"
                  class="block text-xs uppercase tracking-[0.2em] text-text-secondary"
                  >API Key</label
                >
                <input
                  id="remote-api-key"
                  type="password"
                  placeholder="sk-..."
                  class="mt-2 w-full rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary placeholder-text-muted transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
                  value={localEngine.remote_api_key}
                  oninput={handleRemoteApiKeyInput}
                />
                <p class="mt-1 text-xs font-sans text-text-muted">
                  {#if localEngine.remote_api_key && localEngine.remote_api_key !== ''}
                    Key is set — leave blank to keep unchanged
                  {:else}
                    Required for OpenAI, Groq, and most providers
                  {/if}
                </p>
              </div>

              <div>
                <label
                  for="remote-timeout"
                  class="block text-xs uppercase tracking-[0.2em] text-text-secondary"
                  >Request Timeout</label
                >
                <p class="mt-1 text-xs font-sans text-text-muted">
                  Base timeout in seconds — automatically scaled up for large audio files
                </p>
                <div class="mt-2 flex items-center gap-3">
                  <input
                    id="remote-timeout"
                    type="number"
                    min="60"
                    max="3600"
                    step="60"
                    class="w-28 rounded-none border-0 border-b border-text-primary/20 bg-transparent px-0 py-2 text-sm font-sans text-text-primary placeholder-text-muted transition-colors duration-500 ease-luxury focus:border-accent focus:outline-none focus:ring-0"
                    value={localEngine.remote_timeout}
                    oninput={handleRemoteTimeoutInput}
                  />
                  <span class="text-xs font-sans text-text-muted">seconds</span>
                </div>
              </div>
            </div>
          {:else}
            <div
              class="flex items-center gap-3 rounded-none border border-text-primary/10 bg-text-primary/5 px-4 py-3"
            >
              <svg
                class="h-4 w-4 shrink-0 text-text-secondary"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4" />
                <path d="M12 8h.01" />
              </svg>
              <p class="text-xs font-sans text-text-secondary">
                {#if caps.gpu}
                  Using local GPU ({status.gpu_name || caps.device})
                {:else}
                  Using CPU — transcription will be slow. Consider switching to remote.
                {/if}
              </p>
            </div>
          {/if}

          {#if engineDirty}
            <div class="flex justify-end pt-2">
              <button
                type="button"
                onclick={handleSaveEngine}
                disabled={engineSaving}
                class="rounded-none border border-accent bg-accent/10 px-6 py-2 text-xs uppercase tracking-[0.2em] text-accent transition-colors duration-500 ease-luxury hover:bg-accent hover:text-surface-900 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {engineSaving ? 'Applying...' : 'Apply Changes'}
              </button>
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
            {#if localEngine.engine === 'remote'}
              <span class="text-sm font-sans text-text-primary">Remote API</span>
            {:else}
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
            {/if}
          </div>
        </div>
      </section>
    </div>
  {/if}
</div>
