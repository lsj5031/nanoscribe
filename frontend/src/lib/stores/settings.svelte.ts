/**
 * Settings store – UI preferences for transcription settings.
 * Hotwords and language are stored locally; actual API integration is future work.
 */

export type LanguageOption = 'auto' | 'en' | 'zh' | 'ja' | 'ko' | 'de' | 'fr' | 'es' | 'pt' | 'ru';

export const LANGUAGES: { value: LanguageOption; label: string }[] = [
  { value: 'auto', label: 'Auto Detect' },
  { value: 'en', label: 'English' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'de', label: 'German' },
  { value: 'fr', label: 'French' },
  { value: 'es', label: 'Spanish' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'ru', label: 'Russian' }
];

function loadSetting<T>(key: string, fallback: T): T {
  if (typeof localStorage === 'undefined') return fallback;
  const stored = localStorage.getItem(`nanoscribe-settings-${key}`);
  if (stored) {
    try {
      return JSON.parse(stored) as T;
    } catch {
      return fallback;
    }
  }
  return fallback;
}

function saveSetting(key: string, value: unknown): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(`nanoscribe-settings-${key}`, JSON.stringify(value));
}

let diarizationEnabled = $state<boolean>(loadSetting('diarization', true));
let hotwords = $state<string>(loadSetting('hotwords', ''));
let language = $state<LanguageOption>(loadSetting('language', 'auto'));

export function getDiarizationEnabled(): boolean {
  return diarizationEnabled;
}
export function setDiarizationEnabled(v: boolean): void {
  diarizationEnabled = v;
  saveSetting('diarization', v);
}

export function getHotwords(): string {
  return hotwords;
}
export function setHotwords(v: string): void {
  hotwords = v;
  saveSetting('hotwords', v);
}

export function getLanguage(): LanguageOption {
  return language;
}
export function setLanguage(v: LanguageOption): void {
  language = v;
  saveSetting('language', v);
}
