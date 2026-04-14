/**
 * Readiness state management store.
 * Polls GET /api/system/readiness to show model download status on first run.
 */

export interface ModelReadiness {
  name: string;
  loaded: boolean;
  downloading: boolean;
}

export interface ReadinessData {
  ready: boolean;
  models: Record<string, ModelReadiness>;
  device: string;
  gpu_available: boolean;
}

const DEFAULT_READINESS: ReadinessData = {
  ready: false,
  models: {},
  device: 'unknown',
  gpu_available: false
};

let readiness = $state<ReadinessData>({ ...DEFAULT_READINESS });
let loading = $state(true);
let error = $state<string | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;

export function getReadiness(): ReadinessData {
  return readiness;
}

export function getReadinessLoading(): boolean {
  return loading;
}

export function getReadinessError(): string | null {
  return error;
}

export async function fetchReadiness(): Promise<void> {
  try {
    const res = await fetch('/api/system/readiness');
    if (!res.ok) {
      throw new Error(`Failed to fetch readiness: ${res.status}`);
    }
    readiness = await res.json();
    error = null;
  } catch (e) {
    error = e instanceof Error ? e.message : 'Failed to fetch readiness';
  } finally {
    loading = false;
  }
}

/**
 * Start polling readiness at the given interval (ms).
 * Stops automatically when models become ready.
 */
export function startReadinessPolling(intervalMs = 5000): void {
  stopReadinessPolling();
  fetchReadiness();

  pollTimer = setInterval(() => {
    if (readiness.ready) {
      stopReadinessPolling();
      return;
    }
    fetchReadiness();
  }, intervalMs);
}

export function stopReadinessPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
