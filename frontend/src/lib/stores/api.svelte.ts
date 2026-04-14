/**
 * API fetch wrapper with error handling and toast integration.
 */

import { showError } from '$lib/stores/toasts.svelte';

/**
 * Fetch wrapper that shows toast notifications for network and API errors.
 * Returns the Response object so callers can still handle specific status codes.
 */
export async function apiFetch(
  url: string,
  options?: RequestInit,
  opts?: { errorPrefix?: string; showToast?: boolean }
): Promise<Response> {
  const showToast = opts?.showToast ?? true;
  const prefix = opts?.errorPrefix ?? '';

  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    const msg = prefix
      ? `${prefix}: Network error`
      : 'Network error — please check your connection';
    if (showToast) showError(msg);
    throw e;
  }

  return response;
}

/**
 * Fetch JSON with error handling. Shows toast for non-2xx responses.
 * Returns parsed JSON on success, throws on failure.
 */
export async function apiFetchJson<T = unknown>(
  url: string,
  options?: RequestInit,
  opts?: { errorPrefix?: string; showToast?: boolean }
): Promise<T> {
  const response = await apiFetch(url, options, opts);
  const showToast = opts?.showToast ?? true;
  const prefix = opts?.errorPrefix ?? 'Request failed';

  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = body.detail ?? body.error ?? body.message ?? '';
    } catch {
      // ignore parse error
    }
    const msg = detail ? `${prefix}: ${detail}` : `${prefix} (${response.status})`;
    if (showToast) showError(msg);
    throw new Error(msg);
  }

  return response.json();
}
