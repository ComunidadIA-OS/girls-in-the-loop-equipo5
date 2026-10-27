# %% [markdown]
# # Script 1 · Detección de cortes de plano (PySceneDetect)
#
# Divide el vídeo en PLANOS (tomas continuas de cámara). Guarda `planos.csv`,
# que el Script 2 usa para que una misma persona no "cruce" un corte.
#
# Errores típicos que tiene en cuenta:
#  1. Fundidos a negro: el detector normal no los ve bien -> añadimos un detector de fundidos.
#  2. Flashes de cámara, rótulos animados, destellos -> falsos cortes. Se evita con
#     una duración mínima de plano y comparando la imagen de justo antes del "corte"
#     con la de un instante después: si son casi iguales, era un flash, no un corte.
#  3. Movimiento rápido de cámara o zoom -> falsos cortes. Opción METODO = "adaptive".
#  4. Vídeo sin cortes -> devuelve UN plano (no una lista vacía que rompa el Script 2).
#  5. Ruta mal escrita, vídeo que no abre, FPS = 0 -> mensaje claro y se para.
#  6. Vídeo con frecuencia variable (VFR, típico de móviles o descargas) -> aviso,
#     porque los tiempos calculados a partir del nº de fotograma pueden desviarse.
#  7. Planos sospechosamente cortos que sobreviven -> columna `revisar`.
#
# Lo que NO detecta (anotarlo como limitación): pantalla partida, ventanas superpuestas
# (picture-in-picture) y encadenados muy lentos. Hay que revisarlo a ojo con el mosaico.
#
# En VS Code cada bloque "# %%" es una celda: "Run Cell".

# %% [1] Instalar lo que falte (solo la primera vez)
import importlib.util
import subprocess
import sys

for paquete, modulo in [("scenedetect", "scenedetect"), ("opencv-python", "cv2")]:
    if importlib.util.find_spec(modulo) is None:
        print(f"Instalando {paquete}...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", paquete])
        if r.returncode != 0:  # sin permisos en el entorno compartido
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--user", paquete], check=True)
print("Librerías listas.")

# %% [2] Configuración  <- lo único que normalmente hay que tocar
import os
from pathlib import Path

VIDEO = Path(os.environ.get("VIDEO", "/workspace/equipo5/PAULA/prueba_01.mp4"))
SALIDA = Path(os.environ.get("SALIDA", "/workspace/equipo5/resultados_v2")) / VIDEO.stem

METODO = "content"          # "content" (por defecto) o "adaptive" (mejor si la cámara se mueve mucho)
UMBRAL_CONTENT = 27.0       # más bajo = más cortes (y más falsos). Prueba 20-35.
UMBRAL_ADAPTIVE = 3.0       # solo si METODO = "adaptive"
DETECTAR_FUNDIDOS = True    # añade detector de fundidos a negro
UMBRAL_NEGRO = 12           # brillo medio (0-255) por debajo del cual el fotograma es "negro"
DURACION_MIN_PLANO_S = 0.5  # ningún plano puede durar menos
FILTRAR_FLASHES = True      # descarta "cortes" en los que la imagen de antes y la de después son casi iguales
UMBRAL_FLASH = 10.0         # diferencia media de píxeles (0-255) por debajo de la cual NO es un corte
SEGUNDOS_TRAS_CORTE = 0.35  # cuánto después del corte se toma la imagen para comparar
REVISAR_SI_MENOS_DE_S = 1.0 # planos más cortos se marcan para revisar a mano

SALIDA.mkdir(parents=True, exist_ok=True)

# %% [3] Comprobar el vídeo antes de procesar (errores 5 y 6)
import json
import shutil

import cv2

if not VIDEO.is_file():
    raise FileNotFoundError(
        f"No existe el vídeo: {VIDEO}\n"
        "Revisa la ruta (en la VM los archivos están en /workspace/equipo5/...)."
    )

cap = cv2.VideoCapture(str(VIDEO))
if not cap.isOpened():
    raise RuntimeError(f"OpenCV no puede abrir {VIDEO.name}. Prueba a convertirlo:\n"
                       f"ffmpeg -i {VIDEO.name} -c:v libx264 -pix_fmt yuv420p salida.mp4")
FPS = cap.get(cv2.CAP_PROP_FPS)
TOTAL = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()

if FPS <= 0 or TOTAL <= 0:
    raise RuntimeError(f"FPS ({FPS}) o nº de fotogramas ({TOTAL}) no válidos: vídeo dañado o formato raro.")

print(f"Vídeo: {VIDEO.name} | {W}x{H} | {FPS:.2f} fps | {TOTAL} fotogramas | {TOTAL / FPS:.1f} s")

# ¿Frecuencia variable? Comparamos la frecuencia nominal con la media real (ffprobe).
VFR = False
if shutil.which("ffprobe"):
    sonda = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,avg_frame_rate", "-of", "json", str(VIDEO)],
        capture_output=True, text=True,
    )
    try:
        s = json.loads(sonda.stdout)["streams"][0]
        frac = lambda t: (lambda a, b: float(a) / float(b) if float(b) else 0)(*t.split("/"))
        r, avg = frac(s["r_frame_rate"]), frac(s["avg_frame_rate"])
        VFR = avg > 0 and abs(r - avg) / avg > 0.01
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        print("No se pudo comprobar la frecuencia con ffprobe (no es grave).")
if VFR:
    print("⚠️  Frecuencia VARIABLE: los tiempos pueden desviarse. Recomendado convertir antes:\n"
          f"   ffmpeg -i {VIDEO.name} -r {round(FPS)} -c:v libx264 -pix_fmt yuv420p {VIDEO.stem}_cfr.mp4")

# %% [4] Detectar cortes (errores 1, 2, 3 y 4)
from scenedetect import (AdaptiveDetector, ContentDetector, SceneManager,
                         ThresholdDetector, open_video)

min_frames = max(1, round(DURACION_MIN_PLANO_S * FPS))

gestor = SceneManager()
if METODO == "adaptive":
    gestor.add_detector(AdaptiveDetector(adaptive_threshold=UMBRAL_ADAPTIVE, min_scene_len=min_frames))
else:
    gestor.add_detector(ContentDetector(threshold=UMBRAL_CONTENT, min_scene_len=min_frames))
if DETECTAR_FUNDIDOS:
    gestor.add_detector(ThresholdDetector(threshold=UMBRAL_NEGRO, min_scene_len=min_frames))

video = open_video(str(VIDEO))
gestor.detect_scenes(video, show_progress=False)
# start_in_scene=True -> si no hay cortes, devuelve el vídeo entero como un plano
escenas = gestor.get_scene_list(start_in_scene=True)

# %% [5] Tabla de planos + limpieza
import pandas as pd

import numpy as np

def n_frame(tc):   # compatible con versiones nuevas y antiguas de PySceneDetect
    return tc.frame_num if hasattr(tc, "frame_num") else tc.get_frames()

def segundos(tc):
    return tc.seconds if hasattr(tc, "seconds") else tc.get_seconds()

planos = pd.DataFrame([
    {"plano": i, "frame_ini": n_frame(a), "frame_fin": n_frame(b),
     "inicio_s": round(segundos(a), 3), "fin_s": round(segundos(b), 3)}
    for i, (a, b) in enumerate(escenas)
])

if planos.empty:  # seguridad extra (error 4)
    planos = pd.DataFrame([{"plano": 0, "frame_ini": 0, "frame_fin": TOTAL,
                            "inicio_s": 0.0, "fin_s": round(TOTAL / FPS, 3)}])

# Filtro de flashes (error 2): imagen pequeña en gris, antes vs. después del corte
cap = cv2.VideoCapture(str(VIDEO))
def miniatura(n):
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(max(0, n), TOTAL - 1))
    ok, img = cap.read()
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 36)).astype(float) if ok else None

def es_flash(frame_corte):
    if not FILTRAR_FLASHES:
        return False
    antes = miniatura(frame_corte - 1)
    despues = miniatura(frame_corte + round(SEGUNDOS_TRAS_CORTE * FPS))
    if antes is None or despues is None:
        return False
    return float(np.abs(antes - despues).mean()) < UMBRAL_FLASH

# Fusionar con el plano anterior: planos residuales demasiado cortos y falsos cortes por flash
filas, flashes = [], 0
for p in planos.to_dict("records"):
    corto = (p["fin_s"] - p["inicio_s"]) < DURACION_MIN_PLANO_S
    flash = bool(filas) and es_flash(p["frame_ini"])
    if filas and (corto or flash):
        filas[-1]["frame_fin"], filas[-1]["fin_s"] = p["frame_fin"], p["fin_s"]
        flashes += flash
    else:
        filas.append(p)
cap.release()
planos = pd.DataFrame(filas)
if flashes:
    print(f"Descartados {flashes} falsos cortes por flash/destello.")
planos["plano"] = range(len(planos))
planos["duracion_s"] = (planos.fin_s - planos.inicio_s).round(3)
planos["revisar"] = planos.duracion_s < REVISAR_SI_MENOS_DE_S   # error 7
planos["video_id"] = VIDEO.stem
planos["fps"] = FPS
planos["vfr"] = VFR

# Comprobaciones de coherencia: sin huecos ni solapes, y cubren todo el vídeo
assert (planos.frame_ini.iloc[1:].values == planos.frame_fin.iloc[:-1].values).all(), "Hay huecos o solapes entre planos"
assert planos.frame_ini.iloc[0] == 0, "El primer plano no empieza en 0"

planos.to_csv(SALIDA / "planos.csv", index=False)
print(f"{len(planos)} planos | duración media {planos.duracion_s.mean():.1f} s | "
      f"{planos.revisar.sum()} marcados para revisar")
print("Guardado:", SALIDA / "planos.csv")
planos.head(15)

# %% [6] Mosaico para revisar a ojo (fotograma central de cada plano)
import math

import numpy as np

MAX_MINIATURAS = 60
ancho_m = 320
alto_m = max(1, round(H * ancho_m / W))
muestra = planos.head(MAX_MINIATURAS)
columnas = 6
filas_m = math.ceil(len(muestra) / columnas)
mosaico = np.zeros((filas_m * alto_m, columnas * ancho_m, 3), dtype=np.uint8)

cap = cv2.VideoCapture(str(VIDEO))
for k, p in enumerate(muestra.itertuples()):
    cap.set(cv2.CAP_PROP_POS_FRAMES, (p.frame_ini + p.frame_fin) // 2)
    ok, img = cap.read()
    if not ok:
        continue
    img = cv2.resize(img, (ancho_m, alto_m))
    color = (0, 0, 255) if p.revisar else (255, 255, 255)
    cv2.putText(img, f"P{p.plano} {p.inicio_s:.1f}s ({p.duracion_s:.1f}s)", (6, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
    cv2.putText(img, f"P{p.plano} {p.inicio_s:.1f}s ({p.duracion_s:.1f}s)", (6, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
    f, c = divmod(k, columnas)
    mosaico[f * alto_m:(f + 1) * alto_m, c * ancho_m:(c + 1) * ancho_m] = img
cap.release()

ruta_mosaico = SALIDA / "mosaico_planos.jpg"
cv2.imwrite(str(ruta_mosaico), mosaico)
print("Mosaico:", ruta_mosaico, "(en rojo, los planos a revisar)")
if len(planos) > MAX_MINIATURAS:
    print(f"Solo se muestran los primeros {MAX_MINIATURAS} planos.")