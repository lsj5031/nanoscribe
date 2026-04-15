/**
 * Editor state management store.
 * Handles segments, playback state, wavesurfer, and UI preferences.
 */

import { showError, showWarning, showSuccess } from '$lib/stores/toasts.svelte';

export interface Segment {
  id: string;
  ordinal: number;
  start_ms: number;
  end_ms: number;
  text: string;
  speaker_key: string | null;
  confidence: number | null;
  edited: boolean;
}

export interface Speaker {
  id: string;
  speaker_key: string;
  display_name: string;
  color: string;
}

export interface SegmentsResponse {
  memo_id: string;
  revision: number;
  segments: Segment[];
}

export interface MemoDetail {
  id: string;
  title: string;
  source_kind: string;
  source_filename: string;
  duration_ms: number | null;
  language_detected: string | null;
  language_override: string | null;
  status: string;
  speaker_count: number;
  transcript_revision: number;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
  last_edited_at: string | null;
  latest_job: {
    id: string;
    memo_id: string;
    job_type: string;
    status: string;
    stage: string | null;
    progress: number;
    error_code: string | null;
    error_message: string | null;
    attempt_count: number;
    created_at: string;
  } | null;
  exports: Record<string, boolean>;
}

export type PlaybackSpeed = 0.5 | 0.75 | 1 | 1.25 | 1.5 | 2;

const SPEEDS: PlaybackSpeed[] = [0.5, 0.75, 1, 1.25, 1.5, 2];

// Persisted pane width
function loadPaneWidth(): number {
  if (typeof localStorage === 'undefined') return 65;
  const stored = localStorage.getItem('nanoscribe-editor-pane-width');
  if (stored) {
    const val = parseFloat(stored);
    if (!isNaN(val) && val >= 30 && val <= 70) return val;
  }
  return 65;
}

function savePaneWidth(w: number) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem('nanoscribe-editor-pane-width', String(w));
}

function savePlaybackPosition(memoId: string, ms: number) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(`nanoscribe-playback-${memoId}`, String(ms));
}

function loadPlaybackPosition(memoId: string): number | null {
  if (typeof localStorage === 'undefined') return null;
  const stored = localStorage.getItem(`nanoscribe-playback-${memoId}`);
  if (stored) {
    const val = parseFloat(stored);
    if (!isNaN(val) && val >= 0) return val;
  }
  return null;
}

interface EditorState {
  memoId: string;
  memo: MemoDetail | null;
  segments: Segment[];
  speakers: Speaker[];
  revision: number;
  loading: boolean;
  error: string | null;
  isPlaying: boolean;
  currentTimeMs: number;
  durationMs: number;
  playbackSpeed: PlaybackSpeed;
  currentSegmentIndex: number;
  leftPaneWidthPct: number;
  isDraggingDivider: boolean;
  editingSegmentId: string | null;
  saving: boolean;
  saveError: string | null;
  hoveredSegmentIndex: number;
  transcriptSearchOpen: boolean;
  zoomLevel: number;
  /** Active job progress (0–1), null when no job is running. */
  jobProgress: number | null;
  /** Active job stage label, e.g. "transcribing" */
  jobStage: string | null;
  /** Active job sub-detail, e.g. "Chunk 3/12" */
  jobDetail: string | null;
}

let state = $state<EditorState>({
  memoId: '',
  memo: null,
  segments: [],
  speakers: [],
  revision: 0,
  loading: false,
  error: null,
  isPlaying: false,
  currentTimeMs: 0,
  durationMs: 0,
  playbackSpeed: 1,
  currentSegmentIndex: -1,
  leftPaneWidthPct: loadPaneWidth(),
  isDraggingDivider: false,
  editingSegmentId: null,
  saving: false,
  saveError: null,
  hoveredSegmentIndex: -1,
  transcriptSearchOpen: false,
  zoomLevel: loadZoomLevel(),
  jobProgress: null,
  jobStage: null,
  jobDetail: null
});

function loadZoomLevel(): number {
  if (typeof localStorage === 'undefined') return 1;
  const stored = localStorage.getItem('nanoscribe-zoom-level');
  if (stored) {
    const val = parseFloat(stored);
    if (!isNaN(val) && val >= 1 && val <= 8) return val;
  }
  return 1;
}

// Getters
export function getMemoId(): string {
  return state.memoId;
}
export function getMemo(): MemoDetail | null {
  return state.memo;
}
export function getSegments(): Segment[] {
  return state.segments;
}
export function getSpeakers(): Speaker[] {
  return state.speakers;
}
export function getRevision(): number {
  return state.revision;
}
export function getLoading(): boolean {
  return state.loading;
}
export function getError(): string | null {
  return state.error;
}
export function getIsPlaying(): boolean {
  return state.isPlaying;
}
export function getCurrentTimeMs(): number {
  return state.currentTimeMs;
}
export function getDurationMs(): number {
  return state.durationMs;
}
export function getPlaybackSpeed(): PlaybackSpeed {
  return state.playbackSpeed;
}
export function getCurrentSegmentIndex(): number {
  return state.currentSegmentIndex;
}
export function getLeftPaneWidthPct(): number {
  return state.leftPaneWidthPct;
}
export function getIsDraggingDivider(): boolean {
  return state.isDraggingDivider;
}
export function getEditingSegmentId(): string | null {
  return state.editingSegmentId;
}
export function getSaving(): boolean {
  return state.saving;
}
export function getSaveError(): string | null {
  return state.saveError;
}
export function getSpeeds(): PlaybackSpeed[] {
  return SPEEDS;
}
export function getHoveredSegmentIndex(): number {
  return state.hoveredSegmentIndex;
}
export function getTranscriptSearchOpen(): boolean {
  return state.transcriptSearchOpen;
}
export function getZoomLevel(): number {
  return state.zoomLevel;
}
export function getJobProgress(): number | null {
  return state.jobProgress;
}
export function getJobStage(): string | null {
  return state.jobStage;
}
export function getJobDetail(): string | null {
  return state.jobDetail;
}

// Derived
export function hasSegments(): boolean {
  return state.segments.length > 0;
}

// Setters
export function setIsPlaying(v: boolean): void {
  state.isPlaying = v;
}
export function setCurrentTimeMs(ms: number): void {
  state.currentTimeMs = ms;
  _updateCurrentSegment();
  // Persist playback position (throttled via requestAnimationFrame)
  if (state.memoId) {
    _pendingPositionSave = ms;
    if (!_positionSaveTimer) {
      _positionSaveTimer = setTimeout(() => {
        if (state.memoId && _pendingPositionSave !== null) {
          savePlaybackPosition(state.memoId, _pendingPositionSave);
        }
        _positionSaveTimer = null;
        _pendingPositionSave = null;
      }, 2000);
    }
  }
}
export function setDurationMs(ms: number): void {
  state.durationMs = ms;
}
export function setIsDraggingDivider(v: boolean): void {
  state.isDraggingDivider = v;
}

export function setPlaybackSpeed(speed: PlaybackSpeed): void {
  state.playbackSpeed = speed;
}

export function setEditingSegmentId(id: string | null): void {
  state.editingSegmentId = id;
}

export function setHoveredSegmentIndex(i: number): void {
  state.hoveredSegmentIndex = i;
}

export function setTranscriptSearchOpen(open: boolean): void {
  state.transcriptSearchOpen = open;
}

export function toggleTranscriptSearch(): void {
  state.transcriptSearchOpen = !state.transcriptSearchOpen;
}

export function setZoomLevel(level: number): void {
  const clamped = Math.max(1, Math.min(8, level));
  state.zoomLevel = clamped;
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('nanoscribe-zoom-level', String(clamped));
  }
}

export function setLeftPaneWidthPct(pct: number): void {
  const clamped = Math.max(30, Math.min(70, pct));
  state.leftPaneWidthPct = clamped;
  savePaneWidth(clamped);
}

// Autosave debounce timer
let _saveTimer: ReturnType<typeof setTimeout> | null = null;
// Track the last saved text per segment to avoid unnecessary saves
let _pendingSaves: Map<string, string> = new Map();

// Playback position persistence
let _positionSaveTimer: ReturnType<typeof setTimeout> | null = null;
let _pendingPositionSave: number | null = null;

// SSE connection for active job in editor
let _editorEventSource: EventSource | null = null;

/**
 * Update segment text locally and debounce autosave.
 * Optimistically updates the local segment text, then sends a PATCH after 1.5s of inactivity.
 */
export function updateSegmentText(segmentId: string, newText: string): void {
  // Optimistic local update
  const seg = state.segments.find((s) => s.id === segmentId);
  if (!seg) return;
  seg.text = newText;
  seg.edited = true;

  // Track pending save
  _pendingSaves.set(segmentId, newText);
  state.saving = false;
  state.saveError = null;

  // Cancel existing timer and restart debounce
  if (_saveTimer !== null) {
    clearTimeout(_saveTimer);
  }

  _saveTimer = setTimeout(async () => {
    _saveTimer = null;
    await _flushPendingSaves();
  }, 1500);
}

async function _flushPendingSaves(): Promise<void> {
  if (_pendingSaves.size === 0) return;

  const updates = Array.from(_pendingSaves.entries()).map(([segment_id, text]) => ({
    segment_id,
    text
  }));

  // Snapshot and clear pending saves
  _pendingSaves = new Map();
  state.saving = true;
  state.saveError = null;

  try {
    const resp = await fetch(`/api/memos/${state.memoId}/segments`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_revision: state.revision,
        updates
      })
    });

    if (resp.status === 409) {
      // Conflict: refresh segments from server
      // FastAPI wraps the response in a "detail" key
      const conflictData = await resp.json();
      const detail = conflictData.detail ?? conflictData;
      state.revision = detail.current_revision ?? conflictData.current_revision;
      state.segments = detail.current_segments ?? conflictData.current_segments ?? [];
      state.saving = false;
      state.saveError = 'Transcript was modified in another tab. Updated to latest version.';
      showWarning('Transcript was modified in another tab. Your view has been updated.');
      return;
    }

    if (!resp.ok) {
      throw new Error(`Save failed: ${resp.status}`);
    }

    const data = await resp.json();
    state.revision = data.revision;
    state.saving = false;
  } catch (e) {
    state.saving = false;
    state.saveError = e instanceof Error ? e.message : 'Save failed';
    showError('Failed to save changes. Will retry on next edit.');
    // Revert local changes on error
    for (const upd of updates) {
      const seg = state.segments.find((s) => s.id === upd.segment_id);
      if (seg) {
        // We can't perfectly revert, but we can mark the error
      }
    }
  }
}

/**
 * Cancel any pending autosave timer.
 */
export function cancelPendingSave(): void {
  if (_saveTimer !== null) {
    clearTimeout(_saveTimer);
    _saveTimer = null;
  }
  if (_pendingSaves.size > 0) {
    _flushPendingSaves();
  }
}

/**
 * Immediately save any pending changes (e.g., before leaving the page).
 */
export async function flushSave(): Promise<void> {
  if (_saveTimer !== null) {
    clearTimeout(_saveTimer);
    _saveTimer = null;
  }
  await _flushPendingSaves();
}

/**
 * Initialize the editor with a memo ID.
 */
export async function initEditor(memoId: string): Promise<void> {
  state.memoId = memoId;
  state.loading = true;
  state.error = null;

  try {
    const [memoRes, segRes, speakersRes] = await Promise.all([
      fetch(`/api/memos/${memoId}`),
      fetch(`/api/memos/${memoId}/segments`),
      fetch(`/api/memos/${memoId}/speakers`)
    ]);

    if (!memoRes.ok) {
      throw new Error(`Failed to load memo: ${memoRes.status}`);
    }

    state.memo = await memoRes.json();

    if (segRes.ok) {
      const segData: SegmentsResponse = await segRes.json();
      state.segments = segData.segments;
      state.revision = segData.revision;
    }

    if (speakersRes.ok) {
      const speakersData = await speakersRes.json();
      state.speakers = speakersData.speakers ?? [];
    }

    // Set duration from memo metadata
    if (state.memo?.duration_ms) {
      state.durationMs = state.memo.duration_ms;
    }

    // Restore last playback position
    const savedPosition = loadPlaybackPosition(memoId);
    if (savedPosition !== null && savedPosition > 0) {
      state.currentTimeMs = savedPosition;
    }

    // Reconnect SSE if there's an active (non-terminal) job
    if (state.memo?.latest_job?.id) {
      const jobStatus = state.memo.latest_job.status;
      const activeStatuses = ['queued', 'preprocessing', 'transcribing', 'diarizing', 'finalizing'];
      if (activeStatuses.includes(jobStatus)) {
        connectEditorSSE(state.memo.latest_job.id);
      }
    }
  } catch (e) {
    state.error = e instanceof Error ? e.message : 'Failed to load editor';
    showError(state.error);
  } finally {
    state.loading = false;
  }
}

/**
 * Get the full transcript text as a formatted string for copying.
 */
export function getFullTranscriptText(): string {
  return state.segments
    .map((s) => {
      const ts = formatTime(s.start_ms);
      const speaker = getSpeakerDisplayName(s.speaker_key);
      const prefix = speaker ? `[${ts}] ${speaker}: ` : `[${ts}] `;
      return prefix + s.text;
    })
    .join('\n');
}

/**
 * Connect SSE for the active job in the editor (for refresh resilience).
 */
export function connectEditorSSE(jobId: string): void {
  disconnectEditorSSE();

  _editorEventSource = new EventSource(`/api/jobs/${jobId}/events`);

  _editorEventSource.addEventListener('job.completed', () => {
    disconnectEditorSSE();
    state.jobProgress = null;
    state.jobStage = null;
    state.jobDetail = null;
    // Reload data after completion
    if (state.memoId) initEditor(state.memoId);
    showSuccess('Processing completed');
  });

  _editorEventSource.addEventListener('job.failed', (e: MessageEvent) => {
    disconnectEditorSSE();
    state.jobProgress = null;
    state.jobStage = null;
    state.jobDetail = null;
    try {
      const data = JSON.parse(e.data);
      showError(`Processing failed: ${data.error_message ?? 'Unknown error'}`);
    } catch {
      showError('Processing failed');
    }
  });

  _editorEventSource.addEventListener('job.cancelled', () => {
    disconnectEditorSSE();
    state.jobProgress = null;
    state.jobStage = null;
    state.jobDetail = null;
    showWarning('Processing was cancelled');
  });

  _editorEventSource.addEventListener('job.stage', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (state.memo) {
        state.memo.status = data.status ?? state.memo.status;
      }
      state.jobStage = data.stage ?? data.status ?? null;
      state.jobDetail = null;
      state.jobProgress = data.progress ?? state.jobProgress;
    } catch {
      // ignore parse errors
    }
  });

  _editorEventSource.addEventListener('job.progress', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      state.jobProgress = data.progress ?? state.jobProgress;
      if (data.stage) {
        state.jobStage = data.stage;
      }
      if (data.detail) {
        const d = data.detail;
        if (d.chunks_done != null && d.total_chunks != null) {
          state.jobDetail = `Chunk ${d.chunks_done}/${d.total_chunks}`;
        }
      } else {
        state.jobDetail = null;
      }
    } catch {
      // ignore parse errors
    }
  });

  _editorEventSource.onerror = () => {
    // Don't show error toast on SSE disconnect — the job may still be running
    disconnectEditorSSE();
    // Don't clear job state — the job may still be processing server-side
  };
}

function disconnectEditorSSE(): void {
  if (_editorEventSource) {
    _editorEventSource.close();
    _editorEventSource = null;
  }
}

/**
 * Cleanup editor resources (call on unmount).
 */
export function cleanupEditor(): void {
  disconnectEditorSSE();
  if (_positionSaveTimer) {
    clearTimeout(_positionSaveTimer);
    _positionSaveTimer = null;
  }
  if (state.memoId && state.currentTimeMs > 0) {
    savePlaybackPosition(state.memoId, state.currentTimeMs);
  }
}

/**
 * Go to next segment.
 */
export function goToNextSegment(): void {
  if (state.segments.length === 0) return;
  const next = Math.min(state.currentSegmentIndex + 1, state.segments.length - 1);
  state.currentSegmentIndex = next;
}

/**
 * Go to previous segment.
 */
export function goToPrevSegment(): void {
  if (state.segments.length === 0) return;
  const prev = Math.max(state.currentSegmentIndex - 1, 0);
  state.currentSegmentIndex = prev;
}

/**
 * Seek to a specific segment by index. Returns the start_ms for the caller to use.
 */
export function seekToSegment(index: number): number | null {
  if (index < 0 || index >= state.segments.length) return null;
  state.currentSegmentIndex = index;
  return state.segments[index].start_ms;
}

/**
 * Find the current segment based on playback time.
 */
function _updateCurrentSegment(): void {
  if (state.segments.length === 0) return;
  const time = state.currentTimeMs;

  // Find the segment that contains the current time
  let idx = -1;
  for (let i = 0; i < state.segments.length; i++) {
    const seg = state.segments[i];
    if (time >= seg.start_ms && time <= seg.end_ms) {
      idx = i;
      break;
    }
  }

  // If not in any segment, find the nearest upcoming one
  if (idx === -1) {
    for (let i = 0; i < state.segments.length; i++) {
      if (state.segments[i].start_ms > time) {
        idx = i;
        break;
      }
    }
  }

  state.currentSegmentIndex = idx;
}

/**
 * Format milliseconds to MM:SS or H:MM:SS.
 */
export function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Get speaker color for a speaker key. Uses loaded speaker data, falls back to palette.
 */
export function getSpeakerColor(speakerKey: string | null): string {
  if (!speakerKey) return '#6b7280'; // text-muted
  const speaker = state.speakers.find((s) => s.speaker_key === speakerKey);
  if (speaker) return speaker.color;
  const palette = [
    '#00d4ff', // accent/teal
    '#f472b6', // pink
    '#a78bfa', // violet
    '#34d399', // emerald
    '#fbbf24', // amber
    '#fb923c', // orange
    '#60a5fa', // blue
    '#e879f9' // fuchsia
  ];
  let hash = 0;
  for (let i = 0; i < speakerKey.length; i++) {
    hash = speakerKey.charCodeAt(i) + ((hash << 5) - hash);
  }
  return palette[Math.abs(hash) % palette.length];
}

/**
 * Get speaker display name for a speaker key.
 */
export function getSpeakerDisplayName(speakerKey: string | null): string {
  if (!speakerKey) return '';
  const speaker = state.speakers.find((s) => s.speaker_key === speakerKey);
  if (speaker) return speaker.display_name;
  // Fallback: capitalize speaker key
  return speakerKey;
}

/**
 * Rename a speaker by calling PATCH and updating local state.
 */
export async function renameSpeaker(speakerKey: string, newName: string): Promise<void> {
  const speaker = state.speakers.find((s) => s.speaker_key === speakerKey);
  if (!speaker) return;

  const color = speaker.color;

  try {
    const resp = await fetch(`/api/memos/${state.memoId}/speakers`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        updates: [{ speaker_key: speakerKey, display_name: newName, color }]
      })
    });

    if (!resp.ok) {
      throw new Error(`Failed to rename speaker: ${resp.status}`);
    }

    const data = await resp.json();
    state.speakers = data.speakers ?? state.speakers;
  } catch (e) {
    console.error('Failed to rename speaker:', e);
    throw e;
  }
}
