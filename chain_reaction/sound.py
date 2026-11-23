"""Dry bubble-pops in the style of the classic Chain Reaction orb game.

The published game's recordings are not included. Each cue is generated:
a soft plop when an orb is placed, and the same short pop again for every
explosion. A long chain is that pop retriggered, a little higher each time.
"""
from __future__ import annotations
import io
import math
import struct
import time
import wave

RATE = 44100
_PAN = (-0.28, 0.0, 0.28)
_enabled = False
_muted = False
_sounds: dict[str, object] = {}
_last: dict[str, float] = {}


def _noise(i: int) -> float:
    value = (i * 1103515245 + 12345) & 0x7FFFFFFF
    return (value % 10000) / 5000 - 1


def _bubble(start: float, end: float, dur: float, vol: float, *, tick: float = 0.0) -> list[float]:
    """Sine that falls quickly, plus a tiny click. This is the orb pop."""
    count = max(1, int(RATE * dur))
    phase = 0.0
    samples = []
    for i in range(count):
        glide = i / max(1, count - 1)
        freq = start * ((end / max(1.0, start)) ** glide)
        phase += 2 * math.pi * freq / RATE
        attack = min(1.0, i / max(1.0, RATE * 0.0015))
        body = math.exp(-6.5 * glide)
        sample = math.sin(phase)
        if tick:
            sample += tick * _noise(i * 13 + int(start)) * math.exp(-18.0 * glide)
        samples.append(sample * attack * body * vol)
    return samples


def _blip(freq: float, dur: float, vol: float) -> list[float]:
    count = max(1, int(RATE * dur))
    samples = []
    for i in range(count):
        t = i / RATE
        attack = min(1.0, i / max(1.0, RATE * 0.004))
        body = math.exp(-7.0 * t / dur)
        samples.append(math.sin(2 * math.pi * freq * t) * attack * body * vol)
    return samples


def _mix(parts: list[tuple[float, list[float]]]) -> list[float]:
    total = 1
    for start, samples in parts:
        total = max(total, int(start * RATE) + len(samples))
    mixed = [0.0] * total
    for start, samples in parts:
        offset = int(start * RATE)
        for index, sample in enumerate(samples):
            mixed[offset + index] += sample
    return mixed


def _polish(samples: list[float]) -> list[float]:
    shaped = [math.tanh(sample * 1.15) for sample in samples]
    peak = max((abs(sample) for sample in shaped), default=1.0) or 1.0
    gain = 0.9 / peak
    return [sample * gain for sample in shaped]


def _pan(samples: list[float], pan: float) -> tuple[list[float], list[float]]:
    left = math.sqrt(0.5 * (1 - pan))
    right = math.sqrt(0.5 * (1 + pan))
    return [sample * left for sample in samples], [sample * right for sample in samples]


def _wav(left: list[float], right: list[float]) -> bytes:
    count = max(len(left), len(right))
    frames = bytearray()
    for index in range(count):
        l = left[index] if index < len(left) else 0.0
        r = right[index] if index < len(right) else 0.0
        frames += struct.pack("<hh", int(max(-1.0, min(1.0, l)) * 32767), int(max(-1.0, min(1.0, r)) * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return buffer.getvalue()


def _voice(name: str, player: int, intensity: int, hit: bool) -> list[float]:
    # Red sits lower, Green higher, the way each colour can have its own orb sound.
    colour = (0.86, 1.0, 1.16)[player]
    if name == "place":
        start = 540 * colour
        return _bubble(start, start * 0.34, 0.085, 0.7, tick=0.18)
    if name == "explode":
        start = (620 + intensity * 70) * colour
        dur = max(0.034, 0.055 - intensity * 0.002)
        parts = [
            (0.0, _bubble(start, 120, dur, 0.78, tick=0.55)),
            (0.0, _bubble(start * 0.5, 70, dur * 0.8, 0.28)),
        ]
        if hit:
            parts.append((0.0, _bubble(start * 1.45, 220, 0.03, 0.35, tick=0.3)))
        return _mix(parts)
    if name == "win":
        root = 523.25 * colour
        return _mix([
            (0.00, _blip(root, 0.09, 0.45)),
            (0.09, _blip(root * 1.25, 0.09, 0.42)),
            (0.18, _blip(root * 1.5, 0.14, 0.5)),
        ])
    if name == "start":
        return _mix([
            (0.00, _bubble(420, 220, 0.06, 0.4, tick=0.1)),
            (0.07, _bubble(640, 320, 0.07, 0.5, tick=0.12)),
        ])
    if name == "draw":
        return _mix([(0.0, _blip(440, 0.1, 0.35)), (0.11, _blip(330, 0.14, 0.32))])
    if name == "abort":
        return _bubble(180, 60, 0.14, 0.55, tick=0.4)
    if name == "eliminated":
        return _bubble(480 * colour, 90, 0.16, 0.5, tick=0.15)
    if name == "undo":
        return _bubble(180, 520 * colour, 0.08, 0.4, tick=0.12)
    if name == "tick":
        return _bubble(900, 500, 0.04, 0.35, tick=0.1)
    return _bubble(280, 110, 0.06, 0.45, tick=0.25)


def waveform(name: str, *, player: int = 0, intensity: int = 0, hit: bool = False) -> bytes:
    """Build one cue as a stereo WAV byte string."""
    player = max(0, min(2, int(player)))
    intensity = max(0, min(8, int(intensity)))
    samples = _polish(_voice(name, player, intensity, hit))
    left, right = _pan(samples, _PAN[player] if name in ("place", "explode", "win", "eliminated") else 0.0)
    return _wav(left, right)


def enable() -> bool:
    """Open the mixer. Failure leaves the game silent and still playable."""
    global _enabled
    if _enabled:
        return True
    try:
        import pygame
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=256)
        pygame.mixer.set_num_channels(32)
    except Exception:
        _enabled = False
        return False
    _enabled = True
    return True


def set_muted(muted: bool) -> None:
    global _muted
    _muted = muted
    if muted and _enabled:
        try:
            import pygame
            pygame.mixer.stop()
        except Exception:
            pass


def play(name: str, *, player: int = 0, intensity: int = 0, hit: bool = False) -> None:
    if not _enabled or _muted:
        return
    # Short enough that a fast chain still pops on every burst.
    gap = 0.028 if name == "explode" else 0.03
    now = time.monotonic()
    if now - _last.get(name, 0.0) < gap:
        return
    key = f"{name}:{player}:{intensity}:{int(hit)}"
    try:
        import pygame
        sound = _sounds.get(key)
        if sound is None:
            sound = pygame.mixer.Sound(file=io.BytesIO(waveform(name, player=player, intensity=intensity, hit=hit)))
            _sounds[key] = sound
        sound.play()
        _last[name] = now
    except Exception:
        return
