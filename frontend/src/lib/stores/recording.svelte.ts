/**
 * Recording state management store.
 * Handles microphone recording via MediaRecorder API with live timer and audio level.
 */

interface RecordingState {
  isRecording: boolean;
  isPaused: boolean;
  durationMs: number;
  mediaStream: MediaStream | null;
  mediaRecorder: MediaRecorder | null;
  audioBlob: Blob | null;
  permissionState: PermissionState | null;
  error: string | null;
}

let state = $state<RecordingState>({
  isRecording: false,
  isPaused: false,
  durationMs: 0,
  mediaStream: null,
  mediaRecorder: null,
  audioBlob: null,
  permissionState: null,
  error: null
});

let timerInterval: ReturnType<typeof setInterval> | null = null;
let timerStart = 0;
let timerAccumulated = 0;

export function getIsRecording(): boolean {
  return state.isRecording;
}

export function getIsPaused(): boolean {
  return state.isPaused;
}

export function getDurationMs(): number {
  return state.durationMs;
}

export function getMediaStream(): MediaStream | null {
  return state.mediaStream;
}

export function getMediaRecorder(): MediaRecorder | null {
  return state.mediaRecorder;
}

export function getAudioBlob(): Blob | null {
  return state.audioBlob;
}

export function getPermissionState(): PermissionState | null {
  return state.permissionState;
}

export function getError(): string | null {
  return state.error;
}

export function isMediaRecorderSupported(): boolean {
  return typeof MediaRecorder !== 'undefined';
}

function getSupportedMimeType(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

function startTimer() {
  timerStart = Date.now();
  timerAccumulated = state.durationMs;
  timerInterval = setInterval(() => {
    state.durationMs = timerAccumulated + (Date.now() - timerStart);
  }, 100);
}

function stopTimer() {
  if (timerInterval !== null) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function stopStreamTracks() {
  if (state.mediaStream) {
    for (const track of state.mediaStream.getTracks()) {
      track.stop();
    }
    state.mediaStream = null;
  }
}

/**
 * Request microphone permission.
 */
export async function requestPermission(): Promise<void> {
  state.error = null;

  try {
    // Check permission API first
    if (navigator.permissions) {
      const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
      state.permissionState = result.state;
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.permissionState = 'granted';
    state.mediaStream = stream;
  } catch (e) {
    if (e instanceof DOMException) {
      if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
        state.permissionState = 'denied';
        state.error = 'Microphone permission denied. Please allow access in your browser settings.';
      } else {
        state.error = `Microphone error: ${e.message}`;
      }
    } else {
      state.error = e instanceof Error ? e.message : 'Failed to access microphone';
    }
  }
}

/**
 * Start recording from the current media stream.
 */
export function startRecording(): void {
  if (!state.mediaStream) {
    state.error = 'No media stream available. Request permission first.';
    return;
  }

  const mimeType = getSupportedMimeType();
  const options: MediaRecorderOptions = {};
  if (mimeType) options.mimeType = mimeType;

  try {
    const recorder = new MediaRecorder(state.mediaStream, options);
    const chunks: Blob[] = [];

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data.size > 0) {
        chunks.push(e.data);
      }
    };

    recorder.onstop = () => {
      const blobType = mimeType || 'audio/webm';
      state.audioBlob = new Blob(chunks, { type: blobType });
    };

    recorder.onerror = () => {
      state.error = 'Recording error occurred';
      cleanup();
    };

    recorder.start(1000); // collect data every second
    state.mediaRecorder = recorder;
    state.isRecording = true;
    state.isPaused = false;
    state.audioBlob = null;
    state.durationMs = 0;
    state.error = null;

    startTimer();
  } catch (e) {
    state.error = e instanceof Error ? e.message : 'Failed to start recording';
  }
}

/**
 * Pause the current recording.
 */
export function pauseRecording(): void {
  if (state.mediaRecorder?.state === 'recording') {
    state.mediaRecorder.pause();
    state.isPaused = true;
    stopTimer();
  }
}

/**
 * Resume a paused recording.
 */
export function resumeRecording(): void {
  if (state.mediaRecorder?.state === 'paused') {
    state.mediaRecorder.resume();
    state.isPaused = false;
    startTimer();
  }
}

/**
 * Stop recording and create the audio blob.
 */
export function stopRecording(): Promise<void> {
  return new Promise((resolve) => {
    if (!state.mediaRecorder) {
      resolve();
      return;
    }

    const recorder = state.mediaRecorder;

    if (recorder.state === 'recording' || recorder.state === 'paused') {
      recorder.onstop = () => {
        const chunks: Blob[] = [];
        // The ondataavailable already fires during recording; onstop triggers a final flush
        // We need to handle the blob creation after all data is collected
        resolve();
      };

      // Replace the onstop handler with one that also creates the blob
      const mimeType = getSupportedMimeType() || 'audio/webm';
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };

      recorder.onstop = () => {
        state.audioBlob = new Blob(chunks, { type: mimeType });
        stopTimer();
        state.isRecording = false;
        state.isPaused = false;
        resolve();
      };

      recorder.stop();
    } else {
      resolve();
    }
  });
}

/**
 * Discard the current recording and reset state.
 */
export function discardRecording(): void {
  if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
    state.mediaRecorder.stop();
  }
  stopTimer();
  stopStreamTracks();
  state.isRecording = false;
  state.isPaused = false;
  state.durationMs = 0;
  state.mediaRecorder = null;
  state.audioBlob = null;
  state.error = null;
}

/**
 * Submit the recorded audio via the existing upload endpoint.
 */
export async function submitRecording(): Promise<boolean> {
  if (!state.audioBlob) {
    state.error = 'No recording to submit';
    return false;
  }

  const mimeType = state.audioBlob.type || 'audio/webm';
  const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
  const file = new File([state.audioBlob], `recording_${Date.now()}.${ext}`, { type: mimeType });

  const formData = new FormData();
  formData.append('files[]', file);

  try {
    const res = await fetch('/api/memos', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: 'Upload failed' }));
      state.error = body.detail ?? body.error ?? `Upload failed (${res.status})`;
      return false;
    }

    return true;
  } catch (e) {
    state.error = e instanceof Error ? e.message : 'Upload failed';
    return false;
  } finally {
    // Clean up after submission regardless of result
    stopStreamTracks();
    state.mediaRecorder = null;
    state.audioBlob = null;
    state.isRecording = false;
    state.isPaused = false;
    state.durationMs = 0;
  }
}

/**
 * Full cleanup — stop all streams, timers, and reset state.
 */
export function cleanup(): void {
  if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
    state.mediaRecorder.stop();
  }
  stopTimer();
  stopStreamTracks();
  state.isRecording = false;
  state.isPaused = false;
  state.durationMs = 0;
  state.mediaRecorder = null;
  state.audioBlob = null;
  state.permissionState = null;
  state.error = null;
}
