import time
import wave
import numpy as np
import pandas as pd
from faster_whisper import WhisperModel

OUT = "/workspace/equipo5/FIRDAOUS"
AUDIO = f"{OUT}/audio_completo.wav"   # vídeo entero: los tiempos ya coinciden, sin desfase

with wave.open(AUDIO) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

t0 = time.time()
modelo = WhisperModel("large-v3", device="cuda", compute_type="float16")
segmentos, _ = modelo.transcribe(audio, language="es", vad_filter=True, word_timestamps=True)

segs, palabras = [], []
for i, s in enumerate(segmentos):   # se va generando poco a poco
    segs.append({"segmento": i, "inicio_s": round(s.start, 2), "fin_s": round(s.end, 2), "texto": s.text.strip()})
    for p in s.words:
        palabras.append({"segmento": i, "inicio_s": round(p.start, 2), "fin_s": round(p.end, 2), "palabra": p.word.strip()})
    if i % 50 == 0:
        print(f"  segmento {i}, minuto {s.end / 60:.1f}")

pd.DataFrame(segs).to_csv(f"{OUT}/transcripcion_segmentos.csv", index=False)
pd.DataFrame(palabras).to_csv(f"{OUT}/transcripcion_palabras.csv", index=False)
print(f"\n{len(segs)} segmentos, {len(palabras)} palabras en {time.time() - t0:.0f} s")