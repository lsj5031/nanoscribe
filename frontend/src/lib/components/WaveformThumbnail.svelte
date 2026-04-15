<!--
  WaveformThumbnail: Renders a small waveform visualization from waveform JSON data.
  Used in memo cards (grid and list views).
-->
<script lang="ts">
  interface Props {
    url?: string | null;
    class?: string;
  }

  let { url, class: className = '' }: Props = $props();

  let canvas: HTMLCanvasElement | undefined = $state();
  let peaks: number[] | null = null;

  $effect(() => {
    if (url && canvas) {
      loadWaveform(url);
    }
  });

  async function loadWaveform(waveformUrl: string) {
    try {
      const res = await fetch(waveformUrl);
      if (!res.ok) return;
      const data = await res.json();
      // The waveform data can be an array of numbers or array of [min, max] pairs
      if (Array.isArray(data) && data.length > 0) {
        if (typeof data[0] === 'number') {
          peaks = data as number[];
        } else if (Array.isArray(data[0])) {
          // Convert [min, max] pairs to absolute peaks
          peaks = (data as number[][]).map(([min, max]) => Math.max(Math.abs(min), Math.abs(max)));
        }
        drawWaveform();
      }
    } catch {
      // Silently fail - thumbnail is decorative
    }
  }

  function drawWaveform() {
    if (!canvas || !peaks || peaks.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    const barWidth = Math.max(1, width / peaks.length);
    const midY = height / 2;

    ctx.fillStyle = '#D4AF37'; // Gold accent

    for (let i = 0; i < peaks.length; i++) {
      const barHeight = Math.max(1, peaks[i] * height * 0.9);
      const x = (i / peaks.length) * width;
      ctx.fillRect(x, midY - barHeight / 2, Math.max(1, barWidth - 0.5), barHeight);
    }
  }
</script>

<canvas bind:this={canvas} class={className} style="width: 100%; height: 100%;" aria-hidden="true"
></canvas>
