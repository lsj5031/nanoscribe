/**
 * Upload state management store.
 * Handles file upload via POST /api/memos, SSE progress tracking, and cancellation.
 */

import { showError, showWarning } from '$lib/stores/toasts.svelte';
import { getCapabilities } from '$lib/stores/capabilities.svelte';

export interface UploadJob {
  memoId: string;
  jobId: string;
  title: string;
  status: string;
  stage: string;
  progress: number;
  /** Sub-stage detail, e.g. "Chunk 3/12" during transcription */
  detail?: string;
  /** Error message when job fails */
  error_message?: string;
}

interface UploadState {
  active: UploadJob | null;
  error: string | null;
}

const SUPPORTED_EXTENSIONS = new Set(['wav', 'mp3', 'm4a', 'aac', 'webm', 'ogg', 'opus']);

let state = $state<UploadState>({ active: null, error: null });
let eventSource: EventSource | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;

export function getUploadState(): UploadState {
  return state;
}

export function getActiveUpload(): UploadJob | null {
  return state.active;
}

export function getUploadError(): string | null {
  return state.error;
}

export function clearUploadError(): void {
  state.error = null;
}

export function isAudioFile(file: File): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return SUPPORTED_EXTENSIONS.has(ext);
}

export function getUnsupportedFileNames(files: File[]): string[] {
  return files.filter((f) => !isAudioFile(f)).map((f) => f.name);
}

export function getAudioFiles(files: File[]): File[] {
  return files.filter(isAudioFile);
}

/**
 * Upload audio files via POST /api/memos.
 * For single file: sets active upload and tracks progress.
 * For multiple files: uploads all but only tracks the first.
 */
export async function uploadFiles(files: File[]): Promise<void> {
  if (files.length === 0) {
    showError('No files to upload');
    return;
  }

  // Filter audio files
  const audioFiles = getAudioFiles(files);
  const unsupported = getUnsupportedFileNames(files);

  if (audioFiles.length === 0) {
    showError(
      `Unsupported file format${unsupported.length > 1 ? 's' : ''}. Supported: WAV, MP3, M4A, AAC, WebM, OGG, OPUS`
    );
    return;
  }

  if (unsupported.length > 0) {
    // Show warning for unsupported files but continue with valid ones
    showWarning(`Skipped unsupported: ${unsupported.join(', ')}`);
  }

  const formData = new FormData();
  for (const file of audioFiles) {
    formData.append('files[]', file);
  }

  // Auto-enable diarization when the capability is available
  const capabilities = getCapabilities();
  if (capabilities.speaker_diarization) {
    formData.append('enable_diarization', 'true');
  }

  try {
    const res = await fetch('/api/memos', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: 'Upload failed' }));
      showError(body.detail ?? body.error ?? `Upload failed (${res.status})`);
      return;
    }

    const data = await res.json();

    if (data.memos?.length > 0 && data.jobs?.length > 0) {
      // For single file upload, track the job progress
      if (data.memos.length === 1) {
        const memo = data.memos[0];
        const job = data.jobs[0];
        state.active = {
          memoId: memo.id,
          jobId: job.id,
          title: memo.title,
          status: job.status,
          stage: job.stage ?? job.status,
          progress: job.progress ?? 0
        };
        connectSSE(job.id);
      }
    }
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Upload failed');
  }
}

function connectSSE(jobId: string): void {
  disconnectSSE();

  eventSource = new EventSource(`/api/jobs/${jobId}/events`);

  eventSource.addEventListener('job.stage', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (state.active && state.active.jobId === jobId) {
        state.active = {
          ...state.active,
          status: data.status ?? state.active.status,
          stage: data.stage ?? data.status ?? state.active.stage,
          progress: data.progress ?? state.active.progress
        };
      }
    } catch {
      // ignore parse errors
    }
  });

  eventSource.addEventListener('job.progress', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (state.active && state.active.jobId === jobId) {
        let detail: string | undefined;
        if (data.detail) {
          const d = data.detail;
          if (d.chunks_done != null && d.total_chunks != null) {
            detail = `Chunk ${d.chunks_done}/${d.total_chunks}`;
          }
        }
        state.active = {
          ...state.active,
          progress: data.progress ?? state.active.progress,
          detail
        };
      }
    } catch {
      // ignore parse errors
    }
  });

  const handleTerminal = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (state.active && state.active.jobId === jobId) {
        state.active = {
          ...state.active,
          status: data.status ?? 'completed',
          stage: data.stage ?? data.status ?? 'completed',
          progress: data.progress ?? 1.0,
          error_message:
            data.status === 'failed'
              ? (data.error_message ?? state.active.error_message)
              : undefined
        };
        // Auto-dismiss after a short delay (longer for failed so user can read error)
        const delay = data.status === 'failed' ? 4000 : 1500;
        setTimeout(() => {
          if (
            state.active?.jobId === jobId &&
            (state.active.status === 'completed' ||
              state.active.status === 'failed' ||
              state.active.status === 'cancelled')
          ) {
            dismissUpload();
          }
        }, delay);
      }
    } catch {
      // ignore parse errors
    }
    disconnectSSE();
  };

  eventSource.addEventListener('job.completed', handleTerminal);
  eventSource.addEventListener('job.failed', handleTerminal);
  eventSource.addEventListener('job.cancelled', handleTerminal);

  eventSource.onerror = () => {
    // SSE connection lost — try to reconnect after a delay
    disconnectSSE();
    _tryReconnectSSE(jobId);
  };
}

/**
 * Attempt to reconnect SSE after a connection drop.
 * Polls the job status first; if still active, reconnects SSE.
 * Uses exponential backoff up to MAX_RECONNECT_ATTEMPTS.
 */
function _tryReconnectSSE(jobId: string): void {
  if (_reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    // Give up reconnecting — poll one last time to get final status
    _finalPollJobStatus(jobId);
    return;
  }

  _reconnectAttempts++;
  const delay = RECONNECT_BASE_DELAY_MS * Math.pow(1.5, _reconnectAttempts - 1);

  _reconnectTimer = setTimeout(async () => {
    _reconnectTimer = null;
    // Check if the job is still active before reconnecting
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return; // Job not found, stop reconnecting
      const job = await res.json();

      if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
        // Job finished while we were disconnected — update state directly
        if (state.active && state.active.jobId === jobId) {
          state.active = {
            ...state.active,
            status: job.status,
            stage: job.status,
            progress: job.status === 'completed' ? 1.0 : (job.progress ?? state.active.progress)
          };
          // Auto-dismiss after a short delay
          setTimeout(() => {
            if (
              state.active?.jobId === jobId &&
              (state.active.status === 'completed' ||
                state.active.status === 'failed' ||
                state.active.status === 'cancelled')
            ) {
              state.active = null;
            }
          }, 1500);
        }
        return; // No need to reconnect
      }

      // Job is still active — reconnect SSE
      _reconnectAttempts = 0; // Reset on successful poll
      connectSSE(jobId);
    } catch {
      // Fetch failed — try again
      _tryReconnectSSE(jobId);
    }
  }, delay);
}

function disconnectSSE(): void {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  _reconnectAttempts = 0;
}

/**
 * Final fallback: poll the job status one last time after SSE reconnect gives up.
 * If the job is done, update the UI; otherwise clear the overlay so the user isn't stuck.
 */
async function _finalPollJobStatus(jobId: string): Promise<void> {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) {
      // Job not found — clear overlay
      state.active = null;
      return;
    }
    const job = await res.json();

    if (state.active && state.active.jobId === jobId) {
      if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
        state.active = {
          ...state.active,
          status: job.status,
          stage: job.status,
          progress: job.status === 'completed' ? 1.0 : (job.progress ?? state.active.progress),
          error_message:
            job.status === 'failed' ? (job.error_message ?? state.active.error_message) : undefined
        };
        // Auto-dismiss (longer for failed)
        const delay = job.status === 'failed' ? 4000 : 1500;
        setTimeout(() => {
          if (
            state.active?.jobId === jobId &&
            (state.active.status === 'completed' ||
              state.active.status === 'failed' ||
              state.active.status === 'cancelled')
          ) {
            dismissUpload();
          }
        }, delay);
      } else {
        // Job still running but SSE is dead — show a warning
        // and let the user cancel/dismiss
        showWarning('Lost connection — you can cancel and retry from the library');
      }
    }
  } catch {
    // Can't reach server — clear overlay
    state.active = null;
  }
}

/**
 * Cancel the active upload's job.
 */
export async function cancelUpload(): Promise<void> {
  if (!state.active) return;

  try {
    const res = await fetch(`/api/jobs/${state.active.jobId}/cancel`, { method: 'POST' });
    if (res.ok) {
      state.active = {
        ...state.active,
        status: 'cancelled',
        stage: 'cancelled'
      };
      disconnectSSE();
      setTimeout(() => {
        if (state.active?.status === 'cancelled') {
          state.active = null;
        }
      }, 1000);
    }
  } catch {
    // Even if cancel fails, clean up local state
    disconnectSSE();
    state.active = null;
  }
}

/**
 * Dismiss the active upload overlay (e.g., user clicked away after completion).
 */
export function dismissUpload(): void {
  disconnectSSE();
  state.active = null;
}
