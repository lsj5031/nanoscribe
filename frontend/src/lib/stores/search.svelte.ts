/**
 * Global search state management store.
 * Handles search query, results, debounced API calls, and overlay visibility.
 */

import { goto } from '$app/navigation';

export interface SearchResult {
  memo_id: string;
  memo_title: string;
  match_type: 'title' | 'segment';
  segment_id: string | null;
  segment_text: string | null;
  start_ms: number | null;
  end_ms: number | null;
}

let query = $state('');
let results = $state<SearchResult[]>([]);
let total = $state(0);
let loading = $state(false);
let open = $state(false);
let error = $state<string | null>(null);

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

export function getQuery(): string {
  return query;
}

export function getResults(): SearchResult[] {
  return results;
}

export function getTotal(): number {
  return total;
}

export function getLoading(): boolean {
  return loading;
}

export function getOpen(): boolean {
  return open;
}

export function getError(): string | null {
  return error;
}

export function openSearch(): void {
  open = true;
}

export function closeSearch(): void {
  open = false;
  query = '';
  results = [];
  total = 0;
  loading = false;
  error = null;
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
}

export function setQuery(q: string): void {
  query = q;

  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }

  if (!q.trim()) {
    results = [];
    total = 0;
    loading = false;
    error = null;
    return;
  }

  loading = true;
  debounceTimer = setTimeout(() => {
    search();
  }, 300);
}

async function search(): Promise<void> {
  const q = query.trim();
  if (!q) {
    results = [];
    total = 0;
    loading = false;
    return;
  }

  loading = true;
  error = null;

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    if (!res.ok) {
      throw new Error(`Search failed: ${res.status}`);
    }
    const data = await res.json();
    results = data.results ?? [];
    total = data.total ?? 0;
  } catch (e) {
    error = e instanceof Error ? e.message : 'Search failed';
    results = [];
    total = 0;
  } finally {
    loading = false;
  }
}

export function selectResult(result: SearchResult): void {
  closeSearch();

  if (result.match_type === 'title') {
    goto(`/memos/${result.memo_id}`);
  } else {
    const params = new URLSearchParams();
    if (result.segment_id) params.set('segment', result.segment_id);
    if (result.start_ms != null) params.set('t', String(result.start_ms));
    goto(`/memos/${result.memo_id}?${params.toString()}`);
  }
}

/**
 * Format milliseconds to "MM:SS" or "H:MM:SS".
 */
export function formatTimestamp(ms: number | null): string {
  if (ms == null || ms < 0) return '';
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
