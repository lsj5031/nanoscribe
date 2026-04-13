<script lang="ts">
  import { getActiveUpload, cancelUpload, dismissUpload } from '$lib/stores/upload.svelte';

  let cancelling = $state(false);

  const active = $derived(getActiveUpload());

  // Progress ring math
  const RADIUS = 54;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

  let strokeDashoffset = $derived(CIRCUMFERENCE - (active?.progress ?? 0) * CIRCUMFERENCE);

  // Check if job is in a terminal state
  const isTerminal = $derived(
    active?.status === 'completed' || active?.status === 'failed' || active?.status === 'cancelled'
  );

  async function handleCancel() {
    cancelling = true;
    await cancelUpload();
    cancelling = false;
  }

  function handleDismiss() {
    dismissUpload();
  }

  function getStageLabel(stage: string): string {
    switch (stage) {
      case 'queued':
        return 'Queued';
      case 'preprocessing':
        return 'Preprocessing';
      case 'transcribing':
        return 'Transcribing';
      case 'diarizing':
        return 'Identifying speakers';
      case 'finalizing':
        return 'Finalizing';
      case 'completed':
        return 'Complete';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return stage.charAt(0).toUpperCase() + stage.slice(1);
    }
  }

  function getProgressPercent(progress: number): string {
    return `${Math.round(progress * 100)}%`;
  }
</script>

{#if active}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-surface-900/85 backdrop-blur-sm"
    onkeydown={(e) => {
      if (e.key === 'Escape' && isTerminal) handleDismiss();
    }}
  >
    <div class="flex max-w-sm flex-col items-center gap-6 text-center">
      <!-- Progress ring -->
      <div class="relative flex items-center justify-center">
        <svg class="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
          <!-- Background circle -->
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke="var(--color-surface-600)"
            stroke-width="6"
          />
          <!-- Progress arc -->
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke={isTerminal
              ? active.status === 'completed'
                ? 'var(--color-success)'
                : 'var(--color-error)'
              : 'var(--color-accent)'}
            stroke-width="6"
            stroke-linecap="round"
            stroke-dasharray={CIRCUMFERENCE}
            stroke-dashoffset={strokeDashoffset}
            class="transition-[stroke-dashoffset] duration-500 ease-out"
          />
        </svg>
        <div class="absolute flex flex-col items-center">
          <span class="text-2xl font-bold text-text-primary">
            {getProgressPercent(active.progress)}
          </span>
        </div>
      </div>

      <!-- Title and stage -->
      <div class="flex flex-col items-center gap-1">
        <p class="text-lg font-semibold text-text-primary truncate max-w-[280px]">
          {active.title}
        </p>
        <p class="text-sm text-text-secondary">{getStageLabel(active.stage)}</p>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-3">
        {#if isTerminal}
          <button
            onclick={handleDismiss}
            class="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-surface-900 transition-colors hover:bg-accent-hover"
          >
            {active.status === 'completed' ? 'Done' : 'Dismiss'}
          </button>
        {:else}
          <button
            onclick={handleCancel}
            disabled={cancelling}
            class="rounded-lg border border-border bg-surface-700 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-surface-600 disabled:opacity-50"
          >
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}
