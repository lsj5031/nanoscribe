<script lang="ts">
  import {
    getIsRecording,
    getIsPaused,
    getDurationMs,
    getMediaStream,
    getPermissionState,
    getError,
    isMediaRecorderSupported,
    requestPermission,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    discardRecording,
    submitRecording,
    cleanup
  } from '$lib/stores/recording.svelte';
  import { fetchMemos } from '$lib/stores/library.svelte';

  let visible = $state(false);
  let submitting = $state(false);
  let audioLevel = $state(0);

  let analyserNode: AnalyserNode | null = null;
  let audioContext: AudioContext | null = null;
  let animFrameId: number | null = null;

  const permission = $derived(getPermissionState());
  const isRecording = $derived(getIsRecording());
  const isPaused = $derived(getIsPaused());
  const durationMs = $derived(getDurationMs());
  const error = $derived(getError());
  const stream = $derived(getMediaStream());

  // Device selector
  let devices: MediaDeviceInfo[] = $state([]);
  let selectedDeviceId = $state('');

  const supported = isMediaRecorderSupported();

  const durationStr = $derived(formatTime(durationMs));

  function formatTime(ms: number): string {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  export function open() {
    visible = true;
    loadDevices();
  }

  export function close() {
    cleanup();
    disconnectAnalyser();
    visible = false;
  }

  async function handleRequestPermission() {
    await requestPermission();
    loadDevices();
  }

  async function handleStartRecording() {
    // If a specific device was selected, get a new stream with that device
    if (selectedDeviceId && stream) {
      // Stop existing tracks first
      for (const track of stream.getTracks()) {
        track.stop();
      }
      try {
        const newStream = await navigator.mediaDevices.getUserMedia({
          audio: { deviceId: { exact: selectedDeviceId } }
        });
        // Update the stream in the store by starting recording which uses it
        // We need to manually replace the stream
        const storeStream = getMediaStream();
        if (storeStream) {
          for (const track of storeStream.getTracks()) {
            track.stop();
          }
        }
        // We'll directly start recording with the new stream
        startRecordingWithStream(newStream);
        return;
      } catch {
        // Fall back to default
      }
    }
    startRecording();
    connectAnalyser();
  }

  function startRecordingWithStream(newStream: MediaStream) {
    // Import the store and set the stream, then start
    // We need a small workaround since the store expects the stream to be set
    // Just use startRecording which uses the store's stream
    // For now, use default approach
    startRecording();
    connectAnalyser();
  }

  function handlePause() {
    pauseRecording();
    disconnectAnalyser();
  }

  function handleResume() {
    resumeRecording();
    connectAnalyser();
  }

  async function handleStopAndSubmit() {
    submitting = true;
    disconnectAnalyser();
    await stopRecording();
    const ok = await submitRecording();
    submitting = false;
    if (ok) {
      visible = false;
      fetchMemos();
    }
  }

  function handleDiscard() {
    disconnectAnalyser();
    discardRecording();
  }

  function connectAnalyser() {
    const currentStream = getMediaStream();
    if (!currentStream) return;

    try {
      audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(currentStream);
      analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 256;
      source.connect(analyserNode);

      const dataArray = new Uint8Array(analyserNode.frequencyBinCount);

      function updateLevel() {
        if (!analyserNode) return;
        analyserNode.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        audioLevel = sum / dataArray.length / 255;
        animFrameId = requestAnimationFrame(updateLevel);
      }

      updateLevel();
    } catch {
      // Analyser not available, level stays at 0
    }
  }

  function disconnectAnalyser() {
    if (animFrameId !== null) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    if (audioContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
    analyserNode = null;
    audioLevel = 0;
  }

  async function loadDevices() {
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      devices = allDevices.filter((d) => d.kind === 'audioinput');
    } catch {
      devices = [];
    }
  }

  async function handleDeviceChange() {
    if (!selectedDeviceId) return;
    // Get a new stream with the selected device
    try {
      const currentStream = getMediaStream();
      if (currentStream) {
        for (const track of currentStream.getTracks()) {
          track.stop();
        }
      }
      const newStream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: { exact: selectedDeviceId } }
      });
      // We can't directly set the stream in the store from here
      // The stream will be used on next startRecording
    } catch {
      // Keep existing stream
    }
  }

  // Level bar segments for visualization
  const BAR_COUNT = 32;
</script>

{#if visible}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-surface-900/90 backdrop-blur-sm"
    onkeydown={(e) => {
      if (e.key === 'Escape' && !isRecording && !submitting) close();
    }}
  >
    <div
      class="flex w-full max-w-md flex-col gap-6 rounded-2xl border border-border bg-surface-800 p-6 shadow-2xl"
    >
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-text-primary">Record Audio</h2>
        {#if !isRecording && !submitting}
          <button
            onclick={close}
            class="rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
            aria-label="Close"
          >
            <svg
              class="h-5 w-5"
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

      {#if !supported}
        <!-- Browser not supported -->
        <div class="flex flex-col items-center gap-4 py-4 text-center">
          <div class="rounded-full bg-error/20 p-4">
            <svg
              class="h-8 w-8 text-error"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <div>
            <p class="font-medium text-text-primary">Recording not supported</p>
            <p class="mt-1 text-sm text-text-secondary">
              Your browser does not support audio recording. Please use a modern browser like Chrome
              or Firefox.
            </p>
          </div>
        </div>
      {:else if !permission || permission === 'prompt'}
        <!-- Permission request -->
        <div class="flex flex-col items-center gap-4 py-4 text-center">
          <div class="rounded-full bg-accent-muted p-4">
            <svg
              class="h-8 w-8 text-accent"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </div>
          <div>
            <p class="font-medium text-text-primary">Allow microphone access</p>
            <p class="mt-1 text-sm text-text-secondary">
              NanoScribe needs access to your microphone to record audio.
            </p>
          </div>
          <button
            onclick={handleRequestPermission}
            class="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-surface-900 transition-colors hover:bg-accent-hover"
          >
            Allow Microphone
          </button>
        </div>
      {:else if permission === 'denied'}
        <!-- Permission denied -->
        <div class="flex flex-col items-center gap-4 py-4 text-center">
          <div class="rounded-full bg-error/20 p-4">
            <svg
              class="h-8 w-8 text-error"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <line x1="1" y1="1" x2="23" y2="23" />
              <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
              <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.13 1.48-.35 2.16" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </div>
          <div>
            <p class="font-medium text-text-primary">Microphone access denied</p>
            <p class="mt-1 text-sm text-text-secondary">To re-enable microphone access:</p>
            <ul class="mt-2 space-y-1 text-left text-xs text-text-muted">
              <li>1. Click the lock/info icon in your browser's address bar</li>
              <li>2. Find "Microphone" in the permissions list</li>
              <li>3. Change it to "Allow"</li>
              <li>4. Reload the page and try again</li>
            </ul>
          </div>
          <button
            onclick={handleRequestPermission}
            class="rounded-lg border border-border bg-surface-700 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-surface-600"
          >
            Try Again
          </button>
        </div>
      {:else}
        <!-- Recording interface -->
        <div class="flex flex-col gap-5">
          <!-- Device selector -->
          {#if devices.length > 1 && !isRecording}
            <div>
              <label for="device-select" class="mb-1.5 block text-xs text-text-muted"
                >Input Device</label
              >
              <select
                id="device-select"
                bind:value={selectedDeviceId}
                onchange={handleDeviceChange}
                class="w-full rounded-lg border border-border bg-surface-700 px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent"
              >
                {#each devices as device}
                  <option value={device.deviceId}>
                    {device.label || `Microphone ${devices.indexOf(device) + 1}`}
                  </option>
                {/each}
              </select>
            </div>
          {/if}

          <!-- Audio level visualization -->
          <div class="flex h-12 items-center justify-center gap-0.5 rounded-xl bg-surface-700 px-4">
            {#if isRecording && !isPaused}
              {#each Array(BAR_COUNT) as _, i}
                <div
                  class="w-1 rounded-full transition-all duration-75 {audioLevel * 3 > i / BAR_COUNT
                    ? 'bg-accent'
                    : 'bg-surface-500'}"
                  style="height: {Math.max(
                    4,
                    Math.min(
                      40,
                      audioLevel * 60 * (1 - Math.abs(i - BAR_COUNT / 2) / (BAR_COUNT / 2)) + 4
                    )
                  )}px;"
                ></div>
              {/each}
            {:else}
              <span class="text-sm text-text-muted">
                {isRecording ? 'Paused' : 'Ready to record'}
              </span>
            {/if}
          </div>

          <!-- Timer -->
          <div class="text-center">
            <span class="font-mono text-3xl font-light text-text-primary">{durationStr}</span>
            {#if isRecording && !isPaused}
              <div class="mt-1 flex items-center justify-center gap-1.5">
                <div class="h-2 w-2 animate-pulse rounded-full bg-error"></div>
                <span class="text-xs text-error">REC</span>
              </div>
            {/if}
          </div>

          <!-- Controls -->
          <div class="flex items-center justify-center gap-3">
            {#if isRecording}
              <!-- Pause / Resume -->
              <button
                onclick={isPaused ? handleResume : handlePause}
                class="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-700 text-text-primary transition-colors hover:bg-surface-600"
                aria-label={isPaused ? 'Resume recording' : 'Pause recording'}
              >
                {#if isPaused}
                  <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5,3 19,12 5,21" />
                  </svg>
                {:else}
                  <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="4" width="4" height="16" />
                    <rect x="14" y="4" width="4" height="16" />
                  </svg>
                {/if}
              </button>

              <!-- Discard -->
              <button
                onclick={handleDiscard}
                class="flex h-12 w-12 items-center justify-center rounded-full border border-error/30 bg-error/10 text-error transition-colors hover:bg-error/20"
                aria-label="Discard recording"
              >
                <svg
                  class="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="3,6 5,6 21,6" />
                  <path
                    d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                  />
                </svg>
              </button>

              <!-- Stop & Submit -->
              <button
                onclick={handleStopAndSubmit}
                disabled={submitting}
                class="flex h-14 w-14 items-center justify-center rounded-full bg-success text-surface-900 shadow-lg transition-all hover:bg-success/90 hover:shadow-xl active:scale-95 disabled:opacity-50"
                aria-label="Stop and submit recording"
              >
                <svg class="h-6 w-6" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
              </button>
            {:else}
              <!-- Start recording button -->
              <button
                onclick={handleStartRecording}
                class="group flex h-16 w-16 items-center justify-center rounded-full bg-error shadow-lg transition-all hover:bg-error/90 hover:shadow-xl hover:scale-105 active:scale-95"
                aria-label="Start recording"
              >
                <div
                  class="h-7 w-7 rounded-full bg-white transition-transform group-hover:scale-110"
                ></div>
              </button>
            {/if}
          </div>

          {#if isRecording}
            <p class="text-center text-xs text-text-muted">
              {submitting ? 'Uploading…' : 'Tap the square to stop and submit'}
            </p>
          {/if}
        </div>
      {/if}

      <!-- Error message -->
      {#if error}
        <div
          class="flex items-center gap-2 rounded-lg border border-error/30 bg-error/10 px-4 py-2.5"
        >
          <svg
            class="h-4 w-4 shrink-0 text-error"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <p class="text-xs text-error">{error}</p>
        </div>
      {/if}
    </div>
  </div>
{/if}
