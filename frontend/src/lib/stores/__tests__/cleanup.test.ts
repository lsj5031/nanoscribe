/**
 * Unit tests for library.svelte.ts and upload.svelte.ts cleanup() functions.
 * Verifies that cleanup() resets active counts to 0, preventing stale
 * "Active" indicators in the TopBar after navigating away from the library.
 *
 * Tests the actual regression: populate stores with active items → verify
 * count > 0 → call cleanup() → verify count drops to 0.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mock browser APIs needed by the stores at import time ────────────────

class MockEventSource {
  url: string;
  onerror: (() => void) | null = null;
  _listeners: Map<string, Set<Function>> = new Map();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(event: string, handler: Function) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event)!.add(handler);
  }

  close() {
    this._listeners.clear();
  }
}

// @ts-ignore
globalThis.EventSource = MockEventSource;

const store: Record<string, string> = {};
globalThis.localStorage = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = value;
  },
  removeItem: (key: string) => {
    delete store[key];
  },
  clear: () => {
    Object.keys(store).forEach((k) => delete store[k]);
  },
  get length() {
    return Object.keys(store).length;
  },
  key: (index: number) => Object.keys(store)[index] ?? null
};

// ── Helper: build a minimal memo-card + job for fetch mock responses ──────

function makeMemo(
  overrides: Partial<{
    id: string;
    title: string;
    duration_ms: number | null;
    speaker_count: number;
    status: string;
    updated_at: string;
    waveform_url: string | null;
    progress: number;
    stage: string | null;
    error_code: string | null;
    error_message: string | null;
  }> = {}
) {
  return {
    id: 'mock-id',
    title: 'Test Memo',
    duration_ms: 60000,
    speaker_count: 0,
    status: 'completed',
    updated_at: '2026-06-02T00:00:00Z',
    waveform_url: null,
    progress: 1.0,
    stage: null,
    error_code: null,
    error_message: null,
    ...overrides
  };
}

function makeJob(
  overrides: Partial<{
    id: string;
    memo_id: string;
    job_type: string;
    status: string;
    stage: string | null;
    progress: number;
  }> = {}
) {
  return {
    id: 'mock-job-id',
    memo_id: 'mock-id',
    job_type: 'transcribe',
    status: 'queued',
    stage: null,
    progress: 0,
    ...overrides
  };
}

// ── Library store tests ──────────────────────────────────────────────────

describe('library.svelte.ts cleanup()', () => {
  let library: typeof import('$lib/stores/library.svelte');
  const fetchSpy = vi.fn();

  beforeEach(async () => {
    vi.resetModules();
    fetchSpy.mockReset();
    globalThis.fetch = fetchSpy;
    // The library module imports toasts only — no module-level fetches.
    library = await import('$lib/stores/library.svelte');
  });

  it('getActiveJobCount returns 0 on fresh state', () => {
    expect(library.getActiveJobCount()).toBe(0);
  });

  it('getActiveJobCount returns >0 for active memos, then 0 after cleanup()', async () => {
    // Mock fetchMemos to return one transcribing memo
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [makeMemo({ status: 'transcribing', progress: 0.5, stage: 'transcribing' })],
        total: 1
      })
    });

    // After fetchMemos, connectActiveJobSSE fires a poll fetch; mock it.
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ latest_job: null })
    });

    await library.fetchMemos();
    expect(library.getActiveJobCount()).toBe(1);

    // Cleanup should reset count to 0
    library.cleanup();
    expect(library.getActiveJobCount()).toBe(0);
    expect(library.getMemos()).toEqual([]);
    expect(library.getTotal()).toBe(0);
  });

  it('cleanup resets to 0 even with multiple memos, one active', async () => {
    // One active, two completed
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          makeMemo({ id: 'a', status: 'transcribing' }),
          makeMemo({ id: 'b', status: 'completed' }),
          makeMemo({ id: 'c', status: 'completed' })
        ],
        total: 3
      })
    });

    // Poll fetch for connectActiveJobSSE
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ latest_job: null })
    });

    await library.fetchMemos();
    expect(library.getActiveJobCount()).toBe(1);

    library.cleanup();
    expect(library.getActiveJobCount()).toBe(0);
  });

  it('cleanup is idempotent', () => {
    library.cleanup();
    library.cleanup();
    expect(library.getActiveJobCount()).toBe(0);
  });

  it('isActiveStatus correctly classifies statuses', () => {
    expect(library.isActiveStatus('queued')).toBe(true);
    expect(library.isActiveStatus('preprocessing')).toBe(true);
    expect(library.isActiveStatus('transcribing')).toBe(true);
    expect(library.isActiveStatus('diarizing')).toBe(true);
    expect(library.isActiveStatus('finalizing')).toBe(true);
    expect(library.isActiveStatus('completed')).toBe(false);
    expect(library.isActiveStatus('failed')).toBe(false);
    expect(library.isActiveStatus('cancelled')).toBe(false);
  });
});

// ── Upload store tests ──────────────────────────────────────────────────

describe('upload.svelte.ts cleanup()', () => {
  let upload: typeof import('$lib/stores/upload.svelte');
  const fetchSpy = vi.fn();

  beforeEach(async () => {
    vi.resetModules();
    fetchSpy.mockReset();
    // capabilities.svelte.ts auto-fetches twice on import (capabilities + engine settings)
    const capsResponse = {
      ok: true,
      json: async () => ({
        ready: true,
        gpu: false,
        device: 'cpu',
        asr_model: '',
        vad: '',
        timestamps: true,
        speaker_diarization: false,
        hotwords: false,
        language_auto_detect: false,
        recording: false
      })
    };
    fetchSpy.mockResolvedValueOnce(capsResponse); // fetchCapabilities()
    fetchSpy.mockResolvedValueOnce({
      // fetchEngineSettings()
      ok: true,
      json: async () => ({
        engine: 'local',
        remote_url: '',
        remote_api_key: '',
        remote_model: '',
        remote_timeout: 900
      })
    });
    globalThis.fetch = fetchSpy;
    upload = await import('$lib/stores/upload.svelte');
  });

  it('getActiveUploadCount returns 0 on fresh state', () => {
    expect(upload.getActiveUploadCount()).toBe(0);
  });

  it('getActiveUploadCount returns >0 after upload, then 0 after cleanup()', async () => {
    // Mock upload response with one memo + one active job
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        memos: [{ id: 'up-id', title: 'Upload' }],
        jobs: [makeJob({ id: 'up-job', memo_id: 'up-id', status: 'transcribing', progress: 0.3 })]
      })
    });

    const audioFile = new File(['fake-audio'], 'test.wav', { type: 'audio/wav' });
    await upload.uploadFiles([audioFile]);
    expect(upload.getActiveUploadCount()).toBe(1);

    upload.cleanup();
    expect(upload.getActiveUploadCount()).toBe(0);
    expect(upload.getActiveUploads().size).toBe(0);
    expect(upload.getUploadError()).toBeNull();
  });

  it('cleanup is idempotent', () => {
    upload.cleanup();
    upload.cleanup();
    expect(upload.getActiveUploadCount()).toBe(0);
  });

  it('isAudioFile validates supported formats correctly', () => {
    expect(upload.isAudioFile(new File([], 'a.wav'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'b.mp3'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'c.m4a'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'd.aac'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'e.webm'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'f.ogg'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'g.opus'))).toBe(true);
    expect(upload.isAudioFile(new File([], 'h.txt'))).toBe(false);
    expect(upload.isAudioFile(new File([], 'i.pdf'))).toBe(false);
  });
});
