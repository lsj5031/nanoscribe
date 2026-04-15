<!--
  DropOverlay: Global drag-and-drop overlay.
  Shows a visual drop indicator when files are dragged over the app.
  Prevents default browser drag behavior.
-->
<script lang="ts">
  import { uploadFiles } from '$lib/stores/upload.svelte';

  let dragCounter = $state(0);
  let isDragging = $derived(dragCounter > 0);

  function handleDragEnter(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter++;
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter--;
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter = 0;

    if (!e.dataTransfer?.files?.length) return;

    const files = Array.from(e.dataTransfer.files);
    uploadFiles(files);
  }
</script>

<svelte:window
  ondragenter={handleDragEnter}
  ondragleave={handleDragLeave}
  ondragover={handleDragOver}
  ondrop={handleDrop}
/>

{#if isDragging}
  <div
    class="pointer-events-auto fixed inset-0 z-50 flex items-center justify-center bg-surface-900/95"
    role="presentation"
  >
    <div
      class="flex w-full max-w-2xl flex-col items-center gap-8 rounded-none border border-text-primary/20 bg-surface-800 p-12 shadow-[0_2px_8px_rgba(0,0,0,0.02)]"
    >
      <div class="rounded-none border border-text-primary/20 p-6">
        <svg
          class="h-10 w-10 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17,8 12,3 7,8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
      </div>
      <div class="text-center">
        <p class="font-serif text-4xl leading-tight text-text-primary">Drop audio files here</p>
        <p class="mt-4 text-xs uppercase tracking-[0.2em] text-text-secondary">
          WAV, MP3, M4A, AAC, WebM, OGG, OPUS
        </p>
      </div>
    </div>
  </div>
{/if}
