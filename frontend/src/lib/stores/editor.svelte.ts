/**
 * Editor state management store.
 * Handles segments, playback state, wavesurfer, and UI preferences.
 */

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

interface EditorState {
  memoId: string;
  memo: MemoDetail | null;
  segments: Segment[];
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
}

let state = $state<EditorState>({
  memoId: '',
  memo: null,
  segments: [],
  revision: 0,
  loading: false,
  error: null,
  isPlaying: false,
  currentTimeMs: 0,
  durationMs: 0,
  playbackSpeed: 1,
  currentSegmentIndex: -1,
  leftPaneWidthPct: loadPaneWidth(),
  isDraggingDivider: false
});

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
export function getSpeeds(): PlaybackSpeed[] {
  return SPEEDS;
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

export function setLeftPaneWidthPct(pct: number): void {
  const clamped = Math.max(30, Math.min(70, pct));
  state.leftPaneWidthPct = clamped;
  savePaneWidth(clamped);
}

/**
 * Initialize the editor with a memo ID.
 */
export async function initEditor(memoId: string): Promise<void> {
  state.memoId = memoId;
  state.loading = true;
  state.error = null;

  try {
    const [memoRes, segRes] = await Promise.all([
      fetch(`/api/memos/${memoId}`),
      fetch(`/api/memos/${memoId}/segments`)
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

    // Set duration from memo metadata
    if (state.memo?.duration_ms) {
      state.durationMs = state.memo.duration_ms;
    }
  } catch (e) {
    state.error = e instanceof Error ? e.message : 'Failed to load editor';
  } finally {
    state.loading = false;
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
 * Get speaker color for a speaker key. Uses a fixed palette.
 */
export function getSpeakerColor(speakerKey: string | null): string {
  if (!speakerKey) return '#6b7280'; // text-muted
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
