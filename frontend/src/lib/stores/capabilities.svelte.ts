export interface Capabilities {
  ready: boolean;
  gpu: boolean;
  device: string;
  asr_model: string;
  vad: string;
  timestamps: boolean;
  speaker_diarization: boolean;
  hotwords: boolean;
  language_auto_detect: boolean;
  recording: boolean;
}

const DEFAULT_CAPABILITIES: Capabilities = {
  ready: false,
  gpu: false,
  device: 'unknown',
  asr_model: '',
  vad: '',
  timestamps: true,
  speaker_diarization: false,
  hotwords: false,
  language_auto_detect: false,
  recording: false
};

let capabilities = $state<Capabilities>({ ...DEFAULT_CAPABILITIES });
let loading = $state(true);
let error = $state<string | null>(null);

export function getCapabilities(): Capabilities {
  return capabilities;
}

export function getCapabilitiesLoading(): boolean {
  return loading;
}

export function getCapabilitiesError(): string | null {
  return error;
}

export async function fetchCapabilities(): Promise<void> {
  loading = true;
  error = null;
  try {
    const res = await fetch('/api/system/capabilities');
    if (!res.ok) {
      throw new Error(`Failed to fetch capabilities: ${res.status}`);
    }
    capabilities = await res.json();
  } catch (e) {
    error = e instanceof Error ? e.message : 'Failed to fetch capabilities';
    console.error('Failed to fetch capabilities:', e);
  } finally {
    loading = false;
  }
}

// Auto-fetch on import and re-export reactive getters
fetchCapabilities();
