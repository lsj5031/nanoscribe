/**
 * Upload state management store.
 * Handles file upload via POST /api/memos, SSE progress tracking, and cancellation.
 */

export interface UploadJob {
  memoId: string;
  jobId: string;
  title: string;
  status: string;
  stage: string;
  progress: number;
}

interface UploadState {
  active: UploadJob | null;
  error: string | null;
}

const SUPPORTED_EXTENSIONS = new Set(['wav', 'mp3', 'm4a', 'aac', 'webm', 'ogg', 'opus']);

let state = $state<UploadState>({ active: null, error: null });
let eventSource: EventSource | null = null;

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
    state.error = 'No files to upload';
    return;
  }

  // Filter audio files
  const audioFiles = getAudioFiles(files);
  const unsupported = getUnsupportedFileNames(files);

  if (audioFiles.length === 0) {
    state.error = `Unsupported file format${unsupported.length > 1 ? 's' : ''}. Supported: WAV, MP3, M4A, AAC, WebM, OGG, OPUS`;
    return;
  }

  if (unsupported.length > 0) {
    // Show error for unsupported files but continue with valid ones
    state.error = `Skipped unsupported: ${unsupported.join(', ')}`;
    // Auto-clear the non-blocking error after 5 seconds
    setTimeout(() => {
      if (state.error?.startsWith('Skipped unsupported:')) {
        state.error = null;
      }
    }, 5000);
  }

  const formData = new FormData();
  for (const file of audioFiles) {
    formData.append('files[]', file);
  }

  try {
    const res = await fetch('/api/memos', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: 'Upload failed' }));
      state.error = body.detail ?? body.error ?? `Upload failed (${res.status})`;
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
    state.error = e instanceof Error ? e.message : 'Upload failed';
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
        state.active = {
          ...state.active,
          progress: data.progress ?? state.active.progress
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
          progress: data.progress ?? 1.0
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
    } catch {
      // ignore parse errors
    }
    disconnectSSE();
  };

  eventSource.addEventListener('job.completed', handleTerminal);
  eventSource.addEventListener('job.failed', handleTerminal);
  eventSource.addEventListener('job.cancelled', handleTerminal);

  eventSource.onerror = () => {
    // SSE error - don't immediately clear, the job may still be running
    // Just disconnect and the user can cancel if needed
    disconnectSSE();
  };
}

function disconnectSSE(): void {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
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
