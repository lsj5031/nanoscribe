<script lang="ts">
  import { getActiveUpload, cancelUpload, dismissUpload } from '$lib/stores/upload.svelte';
  import { getStatusLabel } from '$lib/stores/library.svelte';

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

  // Check if job is in early stages (queued or at 0% progress)
  const isQueued = $derived(
    !isTerminal && (active?.status === 'queued' || (active?.progress ?? 0) < 0.01)
  );

  async function handleCancel() {
    cancelling = true;
    await cancelUpload();
    cancelling = false;
  }

  function handleDismiss() {
    dismissUpload();
  }

  function getProgressPercent(progress: number): string {
    return `${Math.round(progress * 100)}%`;
  }
</script>

{#if active}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-surface-900/95"
    onkeydown={(e) => {
      if (e.key === 'Escape' && isTerminal) handleDismiss();
    }}
  >
    <div
      class="flex w-full max-w-lg flex-col items-center gap-12 rounded-none border border-text-primary/20 bg-surface-800 p-12 shadow-[0_2px_8px_rgba(0,0,0,0.02)] text-center"
    >
      <!-- Progress ring -->
      <div class="relative flex items-center justify-center">
        <!-- Pulsing glow when queued/at 0% -->
        {#if isQueued}
          <div class="absolute h-32 w-32 animate-pulse rounded-full bg-accent/10"></div>
        {/if}
        <svg class="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
          <!-- Background circle -->
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke="var(--color-text-primary)"
            stroke-opacity="0.1"
            stroke-width="2"
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
            stroke-width="2"
            stroke-linecap="square"
            stroke-dasharray={CIRCUMFERENCE}
            stroke-dashoffset={isQueued ? CIRCUMFERENCE * 0.92 : strokeDashoffset}
            class="transition-[stroke-dashoffset] duration-500 ease-luxury"
          />
        </svg>
        <div class="absolute flex flex-col items-center">
          {#if isQueued}
            <!-- Indeterminate spinner dots when queued -->
            <div class="flex items-center gap-1">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:0ms]"
              ></span>
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:150ms]"
              ></span>
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:300ms]"
              ></span>
            </div>
          {:else}
            <span class="font-serif text-3xl text-text-primary">
              {getProgressPercent(active.progress)}
            </span>
          {/if}
        </div>
      </div>

      <!-- Title and stage -->
      <div class="flex flex-col items-center gap-4">
        <h2 class="font-serif text-3xl leading-tight text-text-primary truncate max-w-[280px]">
          {active.title}
        </h2>
        <div class="flex flex-col items-center gap-1">
          <p class="text-xs uppercase tracking-[0.2em] text-text-secondary">
            {getStatusLabel(active.stage)}
          </p>
          {#if active.detail}
            <p class="text-xs tracking-[0.1em] text-accent">
              {active.detail}
            </p>
          {/if}
          {#if active.status === 'failed' && active.error_message}
            <p class="mt-1 max-w-[240px] text-center text-xs text-error/80">
              {active.error_message}
            </p>
          {/if}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-4">
        {#if isTerminal}
          <button
            onclick={handleDismiss}
            class="rounded-none border border-text-primary/20 bg-transparent px-8 py-3 text-xs uppercase tracking-[0.2em] text-text-primary transition-all duration-500 ease-luxury hover:bg-text-primary hover:text-surface-900"
          >
            {active.status === 'completed' ? 'Done' : 'Dismiss'}
          </button>
        {:else}
          <button
            onclick={handleCancel}
            disabled={cancelling}
            class="rounded-none border border-text-primary/20 bg-transparent px-8 py-3 text-xs uppercase tracking-[0.2em] text-text-primary transition-all duration-500 ease-luxury hover:bg-surface-700 disabled:opacity-50"
          >
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}
