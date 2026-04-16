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

export interface EngineSettings {
  engine: 'local' | 'remote';
  remote_url: string;
  remote_api_key: string;
  remote_model: string;
  remote_timeout: number;
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

const DEFAULT_ENGINE_SETTINGS: EngineSettings = {
  engine: 'local',
  remote_url: '',
  remote_api_key: '',
  remote_model: 'whisper-1',
  remote_timeout: 900
};

let capabilities = $state<Capabilities>({ ...DEFAULT_CAPABILITIES });
let loading = $state(true);
let error = $state<string | null>(null);

let engineSettings = $state<EngineSettings>({ ...DEFAULT_ENGINE_SETTINGS });
let engineLoading = $state(true);
let engineSaving = $state(false);

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

export function getEngineSettings(): EngineSettings {
  return engineSettings;
}

export function getEngineLoading(): boolean {
  return engineLoading;
}

export function getEngineSaving(): boolean {
  return engineSaving;
}

export async function fetchEngineSettings(): Promise<void> {
  engineLoading = true;
  try {
    const res = await fetch('/api/system/settings/engine');
    if (!res.ok) throw new Error(`Failed to fetch engine settings: ${res.status}`);
    engineSettings = await res.json();
  } catch (e) {
    console.error('Failed to fetch engine settings:', e);
  } finally {
    engineLoading = false;
  }
}

export async function saveEngineSettings(settings: EngineSettings): Promise<EngineSettings | null> {
  engineSaving = true;
  try {
    const res = await fetch('/api/system/settings/engine', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Save failed (${res.status})`);
    }
    engineSettings = await res.json();
    // Refresh capabilities since engine may have changed
    await fetchCapabilities();
    return engineSettings;
  } catch (e) {
    console.error('Failed to save engine settings:', e);
    return null;
  } finally {
    engineSaving = false;
  }
}

// Auto-fetch engine settings on import
fetchEngineSettings();
