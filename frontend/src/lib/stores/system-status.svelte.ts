/**
 * System status store – fetches runtime status from GET /api/system/status.
 */

export interface SystemStatus {
  status: string;
  model_loaded: boolean;
  device: string;
  gpu_available: boolean;
  gpu_name: string | null;
  data_dir: string;
  memo_count: number;
  storage_used_mb: number;
  models_cached: string[];
}

const DEFAULT_STATUS: SystemStatus = {
  status: 'loading',
  model_loaded: false,
  device: 'unknown',
  gpu_available: false,
  gpu_name: null,
  data_dir: '/app/data',
  memo_count: 0,
  storage_used_mb: 0,
  models_cached: []
};

let status = $state<SystemStatus>({ ...DEFAULT_STATUS });
let loading = $state(true);
let error = $state<string | null>(null);

export function getSystemStatus(): SystemStatus {
  return status;
}

export function getSystemStatusLoading(): boolean {
  return loading;
}

export function getSystemStatusError(): string | null {
  return error;
}

export async function fetchSystemStatus(): Promise<void> {
  loading = true;
  error = null;
  try {
    const res = await fetch('/api/system/status');
    if (!res.ok) {
      throw new Error(`Failed to fetch status: ${res.status}`);
    }
    status = await res.json();
  } catch (e) {
    error = e instanceof Error ? e.message : 'Failed to fetch status';
    console.error('Failed to fetch system status:', e);
  } finally {
    loading = false;
  }
}

fetchSystemStatus();
