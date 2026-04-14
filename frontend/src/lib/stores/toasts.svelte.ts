/**
 * Toast notification store.
 * Supports error, warning, info, and success toast types with auto-dismiss.
 */

export type ToastType = 'error' | 'warning' | 'info' | 'success';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
  dismissible: boolean;
}

interface ToastOptions {
  type?: ToastType;
  message: string;
  duration?: number;
  dismissible?: boolean;
}

let toasts = $state<Toast[]>([]);
let nextId = 0;

export function getToasts(): Toast[] {
  return toasts;
}

export function addToast(options: ToastOptions): void {
  const id = nextId++;
  const type = options.type ?? 'info';
  const duration = options.duration ?? (type === 'error' ? 7000 : 5000);
  const dismissible = options.dismissible ?? true;

  toasts = [...toasts, { id, type, message: options.message, dismissible }];

  // Auto-dismiss
  setTimeout(() => {
    dismissToast(id);
  }, duration);
}

export function dismissToast(id: number): void {
  toasts = toasts.filter((t) => t.id !== id);
}

export function showError(message: string): void {
  addToast({ type: 'error', message });
}

export function showWarning(message: string): void {
  addToast({ type: 'warning', message });
}

export function showInfo(message: string): void {
  addToast({ type: 'info', message });
}

export function showSuccess(message: string): void {
  addToast({ type: 'success', message });
}
