<script lang="ts">
  import { page } from '$app/stores';

  const memoId = $derived($page.params.memoId ?? '');
</script>

<div class="flex h-full flex-col items-center justify-center px-4">
  <div class="flex max-w-md flex-col items-center gap-4 text-center">
    <div class="rounded-full bg-surface-700 p-4">
      <svg
        class="h-8 w-8 text-text-muted"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14,2 14,8 20,8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10,9 9,9 8,9" />
      </svg>
    </div>
    <div>
      <h2 class="text-xl font-semibold text-text-primary">Memo Editor</h2>
      <p class="mt-2 text-sm text-text-secondary">
        Transcript editor will be available here. Memo ID: <code
          class="rounded bg-surface-700 px-1.5 py-0.5 text-accent">{memoId}</code
        >
      </p>
    </div>
  </div>
</div>
