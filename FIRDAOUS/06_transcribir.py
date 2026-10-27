import time
import wave
import numpy as np
import pandas as pd
from faster_whisper import WhisperModel

OUT = "/workspace/equipo5/FIRDAOUS"
AUDIO = f"{OUT}/audio_prueba.wav"
DESFASE = 1606   # segundo del vídeo donde empieza el audio

# Leer el WAV (16 bits, mono, 16 kHz) y pasarlo a decimales entre -1 y 1, como espera Whisper
with wave.open(AUDIO) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

t0 = time.time()
modelo = WhisperModel("large-v3", device="cuda", compute_type="float16")
segmentos, info = modelo.transcribe(audio, language="es", vad_filter=True)

filas = [{"inicio_s": round(s.start + DESFASE, 2),
          "fin_s": round(s.end + DESFASE, 2),
          "texto": s.text.strip()} for s in segmentos]
df = pd.DataFrame(filas)
df.to_csv(f"{OUT}/transcripcion_prueba.csv", index=False)

print(f"{len(df)} segmentos en {time.time() - t0:.0f} s")
print(df.to_string(index=False))