/**
 * Library state management store.
 * Handles memo listing, SSE-based real-time updates, delete, retry, and view preferences.
 */

export interface MemoCard {
  id: string;
  title: string;
  duration_ms: number | null;
  speaker_count: number;
  status: string;
  updated_at: string;
  waveform_url: string | null;
}

export type ViewMode = 'grid' | 'list';
export type SortMode = 'recent' | 'duration';

interface LibraryState {
  memos: MemoCard[];
  total: number;
  page: number;
  pageSize: number;
  query: string;
  sort: SortMode;
  statusFilter: string | null;
  loading: boolean;
  error: string | null;
}

// Persisted preferences
function loadViewMode(): ViewMode {
  if (typeof localStorage === 'undefined') return 'grid';
  return (localStorage.getItem('nanoscribe-view-mode') as ViewMode) || 'grid';
}

function saveViewMode(mode: ViewMode) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem('nanoscribe-view-mode', mode);
}

let viewMode = $state<ViewMode>(loadViewMode());

let state = $state<LibraryState>({
  memos: [],
  total: 0,
  page: 1,
  pageSize: 50,
  query: '',
  sort: 'recent',
  statusFilter: null,
  loading: false,
  error: null
});

// SSE connections for active jobs
const sseConnections = new Map<string, EventSource>();

export function getMemos(): MemoCard[] {
  return state.memos;
}

export function getTotal(): number {
  return state.total;
}

export function getPage(): number {
  return state.page;
}

export function getPageSize(): number {
  return state.pageSize;
}

export function getQuery(): string {
  return state.query;
}

export function getSort(): SortMode {
  return state.sort;
}

export function getStatusFilter(): string | null {
  return state.statusFilter;
}

export function getLoading(): boolean {
  return state.loading;
}

export function getError(): string | null {
  return state.error;
}

export function getViewMode(): ViewMode {
  return viewMode;
}

export function setViewMode(mode: ViewMode): void {
  viewMode = mode;
  saveViewMode(mode);
}

export function setQuery(q: string): void {
  state.query = q;
  state.page = 1;
  fetchMemos();
}

export function setSort(sort: SortMode): void {
  state.sort = sort;
  state.page = 1;
  fetchMemos();
}

export function setStatusFilter(status: string | null): void {
  state.statusFilter = status;
  state.page = 1;
  fetchMemos();
}

export function setPage(page: number): void {
  state.page = page;
  fetchMemos();
}

/**
 * Fetch memos from the API with current filters.
 */
export async function fetchMemos(): Promise<void> {
  state.loading = true;
  state.error = null;

  const params = new URLSearchParams();
  params.set('page', String(state.page));
  params.set('page_size', String(state.pageSize));
  params.set('sort', state.sort);

  if (state.query.trim()) {
    params.set('q', state.query.trim());
  }
  if (state.statusFilter) {
    params.set('status', state.statusFilter);
  }

  try {
    const res = await fetch(`/api/memos?${params}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch memos: ${res.status}`);
    }
    const data = await res.json();
    state.memos = data.items ?? [];
    state.total = data.total ?? 0;

    // Connect SSE for any active jobs
    connectActiveJobSSE();
  } catch (e) {
    state.error = e instanceof Error ? e.message : 'Failed to load library';
  } finally {
    state.loading = false;
  }
}

/**
 * Delete a memo by ID. Removes from local state immediately.
 */
export async function deleteMemo(memoId: string): Promise<void> {
  // Optimistic removal
  const idx = state.memos.findIndex((m) => m.id === memoId);
  const removed = idx >= 0 ? state.memos.splice(idx, 1)[0] : null;
  state.total = Math.max(0, state.total - 1);

  // Disconnect SSE for this memo's jobs
  disconnectSSE(memoId);

  try {
    const res = await fetch(`/api/memos/${memoId}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 404) {
      throw new Error(`Delete failed: ${res.status}`);
    }
  } catch {
    // Revert on failure
    if (removed && idx >= 0) {
      state.memos.splice(idx, 0, removed);
      state.total += 1;
    }
  }
}

/**
 * Retry a failed memo. Updates status optimistically.
 */
export async function retryMemo(memoId: string): Promise<void> {
  // Optimistic update
  const memo = state.memos.find((m) => m.id === memoId);
  if (!memo) return;

  memo.status = 'queued';

  try {
    const res = await fetch(`/api/memos/${memoId}/retry`, { method: 'POST' });
    if (!res.ok) {
      throw new Error(`Retry failed: ${res.status}`);
    }
    const job = await res.json();

    // Connect SSE for the new job
    connectJobSSE(memoId, job.id);
  } catch {
    // Revert on failure
    memo.status = 'failed';
  }
}

/**
 * Connect SSE for all memos with active (non-terminal) statuses.
 */
function connectActiveJobSSE(): void {
  for (const memo of state.memos) {
    if (isActiveStatus(memo.status)) {
      // We need the job ID to connect SSE. For now, we'll use a different approach:
      // listen for events by polling the memo detail to get the latest job.
      // This is simpler and works well for the library view.
      connectMemoPollSSE(memo.id);
    }
  }
}

function isActiveStatus(status: string): boolean {
  return (
    status === 'queued' ||
    status === 'preprocessing' ||
    status === 'transcribing' ||
    status === 'diarizing' ||
    status === 'finalizing'
  );
}

/**
 * Connect SSE for a specific job, updating the memo card in real-time.
 */
function connectJobSSE(memoId: string, jobId: string): void {
  disconnectSSE(memoId);

  const es = new EventSource(`/api/jobs/${jobId}/events`);
  sseConnections.set(memoId, es);

  const updateMemo = (data: { status?: string; stage?: string; progress?: number }) => {
    const memo = state.memos.find((m) => m.id === memoId);
    if (memo && data.status) {
      memo.status = data.status;
    }
  };

  es.addEventListener('job.stage', (e: MessageEvent) => {
    try {
      updateMemo(JSON.parse(e.data));
    } catch {
      /* ignore */
    }
  });

  const handleTerminal = (e: MessageEvent) => {
    try {
      updateMemo(JSON.parse(e.data));
    } catch {
      /* ignore */
    }
    disconnectSSE(memoId);
  };

  es.addEventListener('job.completed', handleTerminal);
  es.addEventListener('job.failed', handleTerminal);
  es.addEventListener('job.cancelled', handleTerminal);

  es.onerror = () => {
    disconnectSSE(memoId);
  };
}

/**
 * For active memos where we don't have the job ID, fetch the memo detail to get it.
 */
function connectMemoPollSSE(memoId: string): void {
  // Fetch the memo detail to get the latest job ID, then connect SSE
  fetch(`/api/memos/${memoId}`)
    .then((res) => res.json())
    .then((detail) => {
      if (detail.latest_job?.id) {
        connectJobSSE(memoId, detail.latest_job.id);
      }
    })
    .catch(() => {
      // If we can't get the job ID, the memo will refresh on next fetch
    });
}

function disconnectSSE(memoId: string): void {
  const es = sseConnections.get(memoId);
  if (es) {
    es.close();
    sseConnections.delete(memoId);
  }
}

function disconnectAllSSE(): void {
  for (const [key] of sseConnections) {
    disconnectSSE(key);
  }
}

/**
 * Refresh a single memo's data from the API (e.g., after SSE event).
 */
export async function refreshMemo(memoId: string): Promise<void> {
  try {
    const res = await fetch(`/api/memos/${memoId}`);
    if (!res.ok) return;
    const detail = await res.json();
    const idx = state.memos.findIndex((m) => m.id === memoId);
    if (idx >= 0) {
      state.memos[idx] = {
        id: detail.id,
        title: detail.title,
        duration_ms: detail.duration_ms,
        speaker_count: detail.speaker_count,
        status: detail.status,
        updated_at: detail.updated_at,
        waveform_url: state.memos[idx].waveform_url // keep existing waveform URL
      };
    }
  } catch {
    /* ignore */
  }
}

/**
 * Format duration in ms to human-readable string.
 */
export function formatDuration(ms: number | null): string {
  if (ms == null || ms <= 0) return '—';
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Format an ISO timestamp to a relative time string.
 */
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * Get a status badge color class based on the memo status.
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-success/20 text-success';
    case 'failed':
    case 'cancelled':
      return 'bg-error/20 text-error';
    case 'queued':
    case 'preprocessing':
    case 'transcribing':
    case 'diarizing':
    case 'finalizing':
      return 'bg-accent/20 text-accent';
    default:
      return 'bg-surface-600 text-text-muted';
  }
}

/**
 * Get a human-readable status label.
 */
export function getStatusLabel(status: string): string {
  switch (status) {
    case 'queued':
      return 'Queued';
    case 'preprocessing':
      return 'Preprocessing';
    case 'transcribing':
      return 'Transcribing';
    case 'diarizing':
      return 'Diarizing';
    case 'finalizing':
      return 'Finalizing';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    case 'cancelled':
      return 'Cancelled';
    default:
      return status;
  }
}

/**
 * Cleanup all SSE connections (call on unmount).
 */
export function cleanup(): void {
  disconnectAllSSE();
}
