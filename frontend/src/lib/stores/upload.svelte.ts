/**
 * Upload state management store.
 * Handles file upload via POST /api/memos, SSE progress tracking, and cancellation.
 * Supports multiple concurrent uploads with per-job SSE connections.
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
  activeJobs: Map<string, UploadJob>; // keyed by memoId
  error: string | null;
}

const SUPPORTED_EXTENSIONS = new Set(['wav', 'mp3', 'm4a', 'aac', 'webm', 'ogg', 'opus']);

let state = $state<UploadState>({ activeJobs: new Map(), error: null });
let sseConnections = new Map<string, EventSource>(); // keyed by jobId
let _reconnectTimers = new Map<string, ReturnType<typeof setTimeout>>(); // keyed by memoId
let _reconnectAttempts = new Map<string, number>(); // keyed by memoId
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;

export function getUploadState(): UploadState {
  return state;
}

/**
 * Get all active upload jobs as a Map keyed by memoId.
 */
export function getActiveUploads(): Map<string, UploadJob> {
  return state.activeJobs;
}

/**
 * Get count of non-terminal active upload jobs.
 */
export function getActiveUploadCount(): number {
  let count = 0;
  for (const job of state.activeJobs.values()) {
    if (!_isTerminalStatus(job.status)) count++;
  }
  return count;
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

function _isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

/**
 * Upload audio files via POST /api/memos.
 * Tracks all returned memos/jobs with per-job SSE connections.
 * The caller should call library store's fetchMemos() after this resolves
 * to populate the library view.
 */
export async function uploadFiles(files: File[]): Promise<void> {
  if (files.length === 0) {
    showError('No files to upload');
    return;
  }

  const audioFiles = getAudioFiles(files);
  const unsupported = getUnsupportedFileNames(files);

  if (audioFiles.length === 0) {
    showError(
      `Unsupported file format${unsupported.length > 1 ? 's' : ''}. Supported: WAV, MP3, M4A, AAC, WebM, OGG, OPUS`
    );
    return;
  }

  if (unsupported.length > 0) {
    showWarning(`Skipped unsupported: ${unsupported.join(', ')}`);
  }

  const formData = new FormData();
  for (const file of audioFiles) {
    formData.append('files[]', file);
  }

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
      // Track ALL returned memos/jobs
      for (let i = 0; i < data.memos.length; i++) {
        const memo = data.memos[i];
        const job = data.jobs[i];
        if (!memo || !job) continue;

        const uploadJob: UploadJob = {
          memoId: memo.id,
          jobId: job.id,
          title: memo.title,
          status: job.status,
          stage: job.stage ?? job.status,
          progress: job.progress ?? 0
        };
        state.activeJobs.set(memo.id, uploadJob);
        connectSSE(job.id, memo.id);
      }
    }
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Upload failed');
  }
}

/**
 * Connect SSE for a specific job, updating the upload job in real-time.
 */
function connectSSE(jobId: string, memoId: string): void {
  disconnectSSE(jobId, memoId);

  const es = new EventSource(`/api/jobs/${jobId}/events`);
  sseConnections.set(jobId, es);

  const updateJob = (updates: Partial<UploadJob>) => {
    const job = state.activeJobs.get(memoId);
    if (!job || job.jobId !== jobId) return;
    if (updates.status != null) job.status = updates.status;
    if (updates.stage != null) job.stage = updates.stage;
    if (updates.progress != null) job.progress = updates.progress;
    if (updates.error_message != null) job.error_message = updates.error_message;
    if (updates.detail != null) job.detail = updates.detail;
  };

  es.addEventListener('job.stage', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      updateJob({
        status: data.status,
        stage: data.stage ?? data.status,
        progress: data.progress
      });
    } catch {
      // ignore parse errors
    }
  });

  es.addEventListener('job.progress', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      let detail: string | undefined;
      if (data.detail) {
        const d = data.detail;
        if (d.chunks_done != null && d.total_chunks != null) {
          detail = `Chunk ${d.chunks_done}/${d.total_chunks}`;
        }
      }
      updateJob({ progress: data.progress, detail });
    } catch {
      // ignore parse errors
    }
  });

  const handleTerminal = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      updateJob({
        status: data.status ?? 'completed',
        stage: data.stage ?? data.status ?? 'completed',
        progress: data.progress ?? 1.0,
        error_message:
          data.status === 'failed'
            ? (data.error_message ?? state.activeJobs.get(memoId)?.error_message)
            : undefined
      });
      // Auto-dismiss this job after a delay
      const delay = data.status === 'failed' ? 4000 : 1500;
      setTimeout(() => {
        const job = state.activeJobs.get(memoId);
        if (job && _isTerminalStatus(job.status)) {
          state.activeJobs.delete(memoId);
        }
      }, delay);
      disconnectSSE(jobId, memoId);
    } catch {
      // ignore parse errors
    }
  };

  es.addEventListener('job.completed', handleTerminal);
  es.addEventListener('job.failed', handleTerminal);
  es.addEventListener('job.cancelled', handleTerminal);

  es.onerror = () => {
    disconnectSSE(jobId, memoId);
    _tryReconnectSSE(jobId, memoId);
  };
}

/**
 * Attempt to reconnect SSE after a connection drop.
 */
function _tryReconnectSSE(jobId: string, memoId: string): void {
  const attempts = _reconnectAttempts.get(memoId) ?? 0;
  if (attempts >= MAX_RECONNECT_ATTEMPTS) {
    _finalPollJobStatus(jobId, memoId);
    return;
  }

  _reconnectAttempts.set(memoId, attempts + 1);
  const delay = RECONNECT_BASE_DELAY_MS * Math.pow(1.5, attempts);

  const timer = setTimeout(async () => {
    _reconnectTimers.delete(memoId);
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();

      if (_isTerminalStatus(job.status)) {
        const uploadJob = state.activeJobs.get(memoId);
        if (uploadJob) {
          uploadJob.status = job.status;
          uploadJob.stage = job.status;
          uploadJob.progress = job.status === 'completed' ? 1.0 : uploadJob.progress;
          if (job.status === 'failed') {
            uploadJob.error_message = job.error_message ?? uploadJob.error_message;
          }
          setTimeout(() => {
            if (
              state.activeJobs.get(memoId) &&
              _isTerminalStatus(state.activeJobs.get(memoId)!.status)
            ) {
              state.activeJobs.delete(memoId);
            }
          }, 1500);
        }
        return;
      }

      _reconnectAttempts.delete(memoId);
      connectSSE(jobId, memoId);
    } catch {
      _tryReconnectSSE(jobId, memoId);
    }
  }, delay);

  _reconnectTimers.set(memoId, timer);
}

function disconnectSSE(jobId: string, memoId: string): void {
  const es = sseConnections.get(jobId);
  if (es) {
    es.close();
    sseConnections.delete(jobId);
  }
  const timer = _reconnectTimers.get(memoId);
  if (timer) {
    clearTimeout(timer);
    _reconnectTimers.delete(memoId);
  }
  _reconnectAttempts.delete(memoId);
}

/**
 * Final fallback: poll the job status after SSE reconnect gives up.
 */
async function _finalPollJobStatus(jobId: string, memoId: string): Promise<void> {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) {
      state.activeJobs.delete(memoId);
      return;
    }
    const job = await res.json();
    const uploadJob = state.activeJobs.get(memoId);
    if (!uploadJob) return;

    if (_isTerminalStatus(job.status)) {
      uploadJob.status = job.status;
      uploadJob.stage = job.status;
      uploadJob.progress = job.status === 'completed' ? 1.0 : uploadJob.progress;
      if (job.status === 'failed') {
        uploadJob.error_message = job.error_message ?? uploadJob.error_message;
      }
      const delay = job.status === 'failed' ? 4000 : 1500;
      setTimeout(() => {
        if (
          state.activeJobs.get(memoId) &&
          _isTerminalStatus(state.activeJobs.get(memoId)!.status)
        ) {
          state.activeJobs.delete(memoId);
        }
      }, delay);
    } else {
      showWarning('Lost connection — you can cancel and retry from the library');
    }
  } catch {
    state.activeJobs.delete(memoId);
  }
}

/**
 * Cancel the current active upload job.
 * Accepts optional jobId for new callers; falls back to first active for legacy callers.
 */
export async function cancelUpload(jobId?: string): Promise<void> {
  // Find the job by jobId or fall back to first active
  let memoId: string | null = null;
  let targetJobId: string | null = jobId ?? null;
  if (!targetJobId) {
    for (const [mid, job] of state.activeJobs) {
      if (!_isTerminalStatus(job.status)) {
        memoId = mid;
        targetJobId = job.jobId;
        break;
      }
    }
  } else {
    for (const [mid, job] of state.activeJobs) {
      if (job.jobId === targetJobId) {
        memoId = mid;
        break;
      }
    }
  }
  if (!memoId || !targetJobId) return;

  try {
    const res = await fetch(`/api/jobs/${targetJobId}/cancel`, { method: 'POST' });
    if (res.ok) {
      const job = state.activeJobs.get(memoId);
      if (job) {
        job.status = 'cancelled';
        job.stage = 'cancelled';
      }
      disconnectSSE(targetJobId, memoId);
      setTimeout(() => {
        state.activeJobs.delete(memoId);
      }, 1000);
    }
  } catch {
    disconnectSSE(targetJobId, memoId);
    state.activeJobs.delete(memoId);
  }
}

/**
 * Dismiss an upload job, removing it from the active map.
 * Accepts optional jobId for new callers; falls back to first active for legacy callers.
 */
export function dismissUpload(jobId?: string): void {
  let memoId: string | null = null;
  if (jobId) {
    for (const [mid, job] of state.activeJobs) {
      if (job.jobId === jobId) {
        memoId = mid;
        break;
      }
    }
  } else {
    for (const [mid, job] of state.activeJobs) {
      if (!_isTerminalStatus(job.status)) {
        memoId = mid;
        break;
      }
    }
  }
  if (!memoId) return;
  const job = state.activeJobs.get(memoId)!;
  disconnectSSE(job.jobId, memoId);
  state.activeJobs.delete(memoId);
}

/**
 * Cleanup all upload SSE connections and clear stale job data (call on unmount).
 * Clearing activeJobs ensures the TopBar's active-job count resets to 0
 * until new uploads are initiated.
 */
export function cleanup(): void {
  for (const [jobId, es] of sseConnections) {
    es.close();
  }
  sseConnections.clear();
  for (const [, timer] of _reconnectTimers) {
    clearTimeout(timer);
  }
  _reconnectTimers.clear();
  _reconnectAttempts.clear();
  state.activeJobs.clear();
  state.error = null;
}
