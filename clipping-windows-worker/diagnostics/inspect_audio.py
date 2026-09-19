"""Analizar audio: ¿es realmente habla?"""

import wave

import numpy as np

AUDIO = r"data\jobs\a766f7bc-8bbf-4172-9f29-9544bb3bd115\temp\audio.wav"

with wave.open(AUDIO, "rb") as w:
    n = w.getnframes()
    nc = w.getnchannels()
    sw = w.getsampwidth()
    sr = w.getframerate()
    raw = w.readframes(n)

audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

print(f"sr={sr} nc={nc} sw={sw} n={n} duration={n/sr:.2f}s")
print(f"min={audio.min():.4f} max={audio.max():.4f} mean={audio.mean():.4f} std={audio.std():.4f}")
print(f"RMS total={np.sqrt((audio**2).mean()):.4f}")

# Energía en ventanas de 100ms
win = sr // 10
nwin = n // win
energy = np.array([np.sqrt((audio[i*win:(i+1)*win]**2).mean()) for i in range(nwin)])
print(f"\nEnergía por ventanas de 100ms ({nwin} ventanas):")
print(f"  min={energy.min():.4f} max={energy.max():.4f} mean={energy.mean():.4f}")
print(f"  >0.01: {(energy>0.01).sum()} ventanas")
print(f"  >0.05: {(energy>0.05).sum()} ventanas")
print(f"  >0.10: {(energy>0.10).sum()} ventanas")

# ZCR (zero-crossing rate) — discriminante: habla ~0.1, música ~0.05-0.2, ruido blanco ~0.5
sign = np.sign(audio)
sign[sign == 0] = 1
zcr = np.abs(np.diff(sign)).mean() / 2
print(f"\nZCR approx={zcr:.4f}")

# Espectro: energía por banda
from numpy.fft import rfft, rfftfreq
spectrum = np.abs(rfft(audio))
freqs = rfftfreq(len(audio), 1/sr)

bands = [
    (0, 200, "sub"),
    (200, 1000, "low"),
    (1000, 4000, "mid"),
    (4000, 8000, "high"),
    (8000, sr/2, "air"),
]
total = spectrum.sum()
print("\nEnergía por bandas espectrales:")
for lo, hi, name in bands:
    mask = (freqs >= lo) & (freqs < hi)
    e = spectrum[mask].sum()
    print(f"  {lo}-{hi} Hz ({name}): {100*e/total:.1f}%")

# Habla humana concentrada en 200-4000 Hz. Si <60% → no es habla
speech_band = ((freqs >= 200) & (freqs < 4000)).sum()
speech_mask = (freqs >= 200) & (freqs < 4000)
speech_pct = 100 * spectrum[speech_mask].sum() / total
print(f"\n200-4000 Hz (banda de habla típica): {speech_pct:.1f}%")

# Ventanas donde la energía supera cierto umbral: ¿hay pausas largas?
threshold = 0.02
voice = (energy > threshold).astype(int)
# Cambios
edges = np.diff(voice, prepend=0)
n_starts = edges.sum()  # cambios 0->1
print(f"\nSegmentos de 'actividad' (>0.02 RMS): {n_starts}")
# Tamaño medio
if n_starts > 0:
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    if len(ends) > 0 and (len(ends) > len(starts) or ends[0] < starts[0]):
        # Termina con silencio, ajustar
        pass
    durs = []
    for s in starts:
        e = ends[ends > s]
        if len(e) > 0:
            durs.append((e[0] - s) * 0.1)
        else:
            durs.append((nwin - s) * 0.1)
    durs = np.array(durs)
    print(f"  Duración media: {durs.mean():.2f}s, max={durs.max():.2f}s, total={durs.sum():.2f}s")
    print(f"  Distribución: <0.5s={(durs<0.5).sum()}, 0.5-2s={((durs>=0.5)&(durs<2)).sum()}, >2s={(durs>=2).sum()}")
