import { useEffect, useRef, useState } from 'react';
import { Play, Pause } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

const fmt = (s) => {
  if (!s || Number.isNaN(s)) return '0:00';
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, '0')}`;
};

export const WaveformAudioPlayer = ({ src, label = 'Stylist audio reply' }) => {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setCurrent(a.currentTime);
    const onLoad = () => setDuration(a.duration || 0);
    const onEnd = () => { setPlaying(false); setCurrent(0); };
    a.addEventListener('timeupdate', onTime);
    a.addEventListener('loadedmetadata', onLoad);
    a.addEventListener('ended', onEnd);
    return () => {
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('loadedmetadata', onLoad);
      a.removeEventListener('ended', onEnd);
    };
  }, [src]);

  const toggle = async () => {
    const a = audioRef.current; if (!a) return;
    if (playing) { a.pause(); setPlaying(false); }
    else { try { await a.play(); setPlaying(true); } catch (_e) { /* ignore */ } }
  };

  return (
    <div
      data-testid="stylist-reply-audio-player"
      className="flex items-center gap-3 rounded-xl border border-border bg-card p-3"
      aria-label={label}
    >
      <Button
        size="icon"
        onClick={toggle}
        aria-label={playing ? 'Pause' : 'Play'}
        data-testid="audio-player-play-button"
        className="rounded-full h-10 w-10 bg-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/90 text-[hsl(var(--accent-foreground))]"
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <div className="flex-1">
        <Slider
          value={[duration ? (current / duration) * 100 : 0]}
          onValueChange={(v) => {
            const a = audioRef.current;
            if (a && duration) a.currentTime = (v[0] / 100) * duration;
          }}
          max={100}
          step={0.1}
          data-testid="audio-player-scrubber"
          aria-valuetext={`${fmt(current)} of ${fmt(duration)}`}
        />
        <div className="flex justify-between text-[11px] text-muted-foreground mt-1">
          <span>{fmt(current)}</span>
          <span>{fmt(duration)}</span>
        </div>
      </div>
      <audio ref={audioRef} src={src} preload="metadata" />
    </div>
  );
};
