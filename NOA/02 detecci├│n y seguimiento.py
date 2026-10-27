# %% [markdown]
# # Script 2 · Detección y seguimiento de personas (YOLO11 + ByteTrack)
#
# Detecta personas en cada fotograma analizado y les da un identificador que se mantiene
# en el tiempo (track). Si existe `planos.csv` (Script 1), parte los tracks en cada corte.
#
# Errores típicos que tiene en cuenta:
#  1. Sin GPU -> sigue en CPU, avisa y recomienda un modelo más pequeño.
#  2. Track fragmentado: alguien se tapa un instante y vuelve con OTRO número.
#     -> ajustamos la "memoria" de ByteTrack (track_buffer) a segundos reales.
#  3. Track que cruza un corte de plano (el tracker reutiliza un número tras el corte)
#     -> se parte usando planos.csv.
#  4. "Fantasmas": tracks de muy poca duración (errores del detector) -> se marcan y se excluyen
#     del resumen.
#  5. Multitudes / personas diminutas al fondo inflan el recuento
#     -> columna `fondo` (área < AREA_FONDO_PCT). No se borran: se decide luego.
#  6. Falsos positivos: personas en fotos, carteles o pantallas del plató
#     -> se marcan tracks casi inmóviles y de tamaño constante como `posible_imagen`.
#  7. Personas cortadas por el borde del encuadre (medidas de tamaño engañosas)
#     -> `pct_toca_borde`.
#  8. Cajas que se salen de la imagen -> se recortan a los límites.
#  9. Duplicados (mismo track dos veces en el mismo fotograma) -> comprobación.
# 10. Vídeo largo que se corta a mitad -> guardado parcial cada cierto tiempo.
# 11. Ninguna persona detectada -> mensaje claro.
#
# En VS Code cada bloque "# %%" es una celda: "Run Cell".

# %% [1] Instalar lo que falte (solo la primera vez)
import importlib.util
import subprocess
import sys

for paquete, modulo in [("ultralytics", "ultralytics"), ("opencv-python", "cv2"), ("pyyaml", "yaml")]:
    if importlib.util.find_spec(modulo) is None:
        print(f"Instalando {paquete}...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", paquete])
        if r.returncode != 0:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--user", paquete], check=True)
print("Librerías listas.")

# %% [2] Configuración  <- lo único que normalmente hay que tocar
import os
from pathlib import Path

VIDEO = Path(os.environ.get("VIDEO", "/workspace/equipo5/PAULA/prueba_01.mp4"))
SALIDA = Path(os.environ.get("SALIDA", "/workspace/equipo5/resultados_v2")) / VIDEO.stem
MODELO = os.environ.get("MODELO", "yolo11m.pt")  # n (rápido) < s < m < l < x (preciso)

MUESTRAS_POR_SEGUNDO = 10   # fotogramas analizados por segundo
CONF_MIN = 0.40             # confianza mínima de una detección
MEMORIA_TRACK_S = 2.0       # segundos que ByteTrack "recuerda" a alguien que desaparece
MIN_TRACK_S = 0.5           # tracks más cortos = fantasmas
AREA_FONDO_PCT = 1.0        # personas que ocupan < 1 % de la pantalla = fondo
MARGEN_BORDE_PX = 3         # caja a menos de 3 px del borde = persona cortada
GUARDAR_CADA_S = 60         # guardado parcial cada 60 s de vídeo

SALIDA.mkdir(parents=True, exist_ok=True)

# %% [3] Comprobar vídeo, GPU y planos (errores 1 y 3)
import cv2
import pandas as pd
import torch

if not VIDEO.is_file():
    raise FileNotFoundError(f"No existe el vídeo: {VIDEO}")
cap = cv2.VideoCapture(str(VIDEO))
if not cap.isOpened():
    raise RuntimeError(f"OpenCV no puede abrir {VIDEO.name}.")
FPS = cap.get(cv2.CAP_PROP_FPS)
TOTAL = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()
if FPS <= 0 or TOTAL <= 0:
    raise RuntimeError("FPS o nº de fotogramas no válidos.")

STRIDE = max(1, round(FPS / MUESTRAS_POR_SEGUNDO))
FPS_ANALISIS = FPS / STRIDE
print(f"{VIDEO.name}: {W}x{H}, {FPS:.2f} fps, {TOTAL / FPS:.1f} s -> analizamos 1 de cada {STRIDE} "
      f"({FPS_ANALISIS:.1f} por segundo)")

if torch.cuda.is_available():
    DISPOSITIVO = 0
    print("GPU:", torch.cuda.get_device_name(0))
else:
    DISPOSITIVO = "cpu"
    print("⚠️  Sin GPU: irá lento. Para pruebas usa MODELO = 'yolo11n.pt'.")

ruta_planos = SALIDA / "planos.csv"
if ruta_planos.exists():
    planos = pd.read_csv(ruta_planos)
    print(f"Usando {len(planos)} planos de {ruta_planos.name}")
else:
    planos = pd.DataFrame([{"plano": 0, "frame_ini": 0, "frame_fin": TOTAL}])
    print("⚠️  No hay planos.csv: ejecuta antes el Script 1. Se trata el vídeo como un único plano.")

# %% [4] Configurar ByteTrack (error 2)
# track_buffer = nº de fotogramas ANALIZADOS que el tracker espera antes de dar a alguien por perdido.
# Por defecto son 30; como analizamos ~10/s, lo pasamos a segundos reales.
import yaml
from ultralytics.utils import ROOT

with open(ROOT / "cfg" / "trackers" / "bytetrack.yaml", encoding="utf-8") as f:
    cfg_tracker = yaml.safe_load(f)
cfg_tracker["track_buffer"] = max(1, round(MEMORIA_TRACK_S * FPS_ANALISIS))
ruta_tracker = SALIDA / "bytetrack_ajustado.yaml"
with open(ruta_tracker, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg_tracker, f)
print("ByteTrack:", {k: cfg_tracker[k] for k in ("track_high_thresh", "track_buffer", "match_thresh") if k in cfg_tracker})

# %% [5] Detectar y seguir (errores 8, 10 y 11)
from ultralytics import YOLO

modelo = YOLO(MODELO)  # se descarga solo la primera vez
resultados = modelo.track(
    str(VIDEO), classes=[0], conf=CONF_MIN, tracker=str(ruta_tracker),
    vid_stride=STRIDE, stream=True, verbose=False, device=DISPOSITIVO, persist=True,
)

ruta_det = SALIDA / "detecciones.csv"
filas, siguiente_guardado = [], GUARDAR_CADA_S
for i, r in enumerate(resultados):
    frame_index = i * STRIDE
    t = frame_index / FPS
    if r.boxes is not None and r.boxes.id is not None:
        for caja, tid, conf in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(), r.boxes.conf.tolist()):
            x1, y1, x2, y2 = caja
            x1, x2 = max(0.0, x1), min(float(W), x2)    # error 8
            y1, y2 = max(0.0, y1), min(float(H), y2)
            if x2 <= x1 or y2 <= y1:
                continue
            filas.append(dict(video_id=VIDEO.stem, frame_index=frame_index, timestamp_s=round(t, 3),
                              track_yolo=tid, conf=round(conf, 4), x1=x1, y1=y1, x2=x2, y2=y2))
    if t >= siguiente_guardado:                       # error 10
        pd.DataFrame(filas).to_csv(SALIDA / "detecciones_parcial.csv", index=False)
        print(f"  ... {t:.0f} s procesados ({len(filas)} detecciones)")
        siguiente_guardado += GUARDAR_CADA_S

det = pd.DataFrame(filas)
if det.empty:                                         # error 11
    raise RuntimeError("No se ha detectado ninguna persona. Revisa el vídeo o baja CONF_MIN.")
print(f"{len(det)} detecciones | {det.track_yolo.nunique()} tracks de ByteTrack")

# %% [6] Partir por plano y calcular medidas (errores 3, 5, 7 y 9)
inicios = planos.sort_values("frame_ini").frame_ini.to_numpy()
det["plano"] = inicios.searchsorted(det.frame_index.to_numpy(), side="right") - 1
det["track_id"] = det.track_yolo.astype(str) + "_p" + det.plano.astype(str)

det["area_pct"] = 100 * (det.x2 - det.x1) * (det.y2 - det.y1) / (W * H)
det["cx"] = (det.x1 + det.x2) / 2 / W
det["cy"] = (det.y1 + det.y2) / 2 / H
det["centralidad"] = 1 - 2 * (det.cx - 0.5).abs()   # 1 = centro, 0 = borde lateral
det["fondo"] = det.area_pct < AREA_FONDO_PCT        # error 5
det["toca_borde"] = ((det.x1 <= MARGEN_BORDE_PX) | (det.x2 >= W - MARGEN_BORDE_PX) |
                     (det.y1 <= MARGEN_BORDE_PX) | (det.y2 >= H - MARGEN_BORDE_PX))  # error 7

duplicados = det.duplicated(["frame_index", "track_id"]).sum()   # error 9
if duplicados:
    print(f"⚠️  {duplicados} duplicados (mismo track en el mismo fotograma): se queda el de mayor confianza.")
    det = det.sort_values("conf", ascending=False).drop_duplicates(["frame_index", "track_id"])
det = det.sort_values(["frame_index", "track_id"]).reset_index(drop=True)
assert det.timestamp_s.is_monotonic_increasing, "Los tiempos no son crecientes"

det.drop(columns=["cx", "cy"]).to_csv(ruta_det, index=False)
(SALIDA / "detecciones_parcial.csv").unlink(missing_ok=True)
print(f"{det.track_id.nunique()} tracks tras partir por plano | guardado {ruta_det}")

# %% [7] Resumen por persona (errores 4 y 6)
por_track = det.groupby("track_id").agg(
    plano=("plano", "first"),
    inicio_s=("timestamp_s", "min"),
    fin_s=("timestamp_s", "max"),
    muestras=("frame_index", "nunique"),
    conf_media=("conf", "mean"),
    area_media_pct=("area_pct", "mean"),
    area_variacion=("area_pct", lambda a: a.std() / a.mean() if len(a) > 1 and a.mean() > 0 else 0),
    movimiento=("cx", lambda c: c.std() if len(c) > 1 else 0),
    movimiento_y=("cy", lambda c: c.std() if len(c) > 1 else 0),
    centralidad_media=("centralidad", "mean"),
    pct_fondo=("fondo", "mean"),
    pct_toca_borde=("toca_borde", "mean"),
)
por_track["tiempo_pantalla_s"] = por_track.muestras / FPS_ANALISIS
por_track["fantasma"] = por_track.tiempo_pantalla_s < MIN_TRACK_S        # error 4
# Error 6: casi no se mueve, tamaño casi constante y aparece bastante tiempo -> ¿foto/cartel/pantalla?
# OJO: un presentador sentado también puede cumplirlo. Es una marca para REVISAR, no para borrar.
por_track["posible_imagen"] = ((por_track.movimiento < 0.005) & (por_track.movimiento_y < 0.005) &
                               (por_track.area_variacion < 0.03) & (por_track.tiempo_pantalla_s >= 3))

por_track = por_track.sort_values("tiempo_pantalla_s", ascending=False)
por_track.round(3).to_csv(SALIDA / "resumen_tracks.csv")

validos = por_track[~por_track.fantasma]
print(f"Tracks totales: {len(por_track)} | fantasmas: {por_track.fantasma.sum()} | "
      f"válidos: {len(validos)} | de fondo (>50 % del tiempo): {(validos.pct_fondo > 0.5).sum()} | "
      f"posibles imágenes: {validos.posible_imagen.sum()}")
validos.round(2).head(15)

# %% [8] Vídeo de revisión (primeros N segundos) para comprobar a ojo
# Colores: verde = válido, gris = fondo, rojo = fantasma, morado = posible imagen
LIMITE_S = 60
crudo, final = SALIDA / "revision_raw.mp4", SALIDA / "revision.mp4"
estado = {}
for tid, fila in por_track.iterrows():
    if fila.fantasma:
        estado[tid] = ((0, 0, 255), "fantasma")
    elif fila.posible_imagen:
        estado[tid] = ((200, 0, 200), "imagen?")
    elif fila.pct_fondo > 0.5:
        estado[tid] = ((160, 160, 160), "fondo")
    else:
        estado[tid] = ((0, 200, 0), "")

vw = cv2.VideoWriter(str(crudo), cv2.VideoWriter_fourcc(*"mp4v"), FPS_ANALISIS, (W, H))
cap = cv2.VideoCapture(str(VIDEO))
por_frame = dict(tuple(det[det.timestamp_s <= LIMITE_S].groupby("frame_index")))
for f in range(0, min(TOTAL, int(LIMITE_S * FPS) + 1), STRIDE):
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok, img = cap.read()
    if not ok:
        break
    for d in por_frame.get(f, pd.DataFrame()).itertuples():
        color, etiqueta = estado[d.track_id]
        cv2.rectangle(img, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 2)
        cv2.putText(img, f"{d.track_id} {etiqueta}", (int(d.x1) + 3, max(15, int(d.y1) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    plano = int(inicios.searchsorted(f, side="right") - 1)
    cv2.putText(img, f"t={f / FPS:5.1f}s  plano {plano}", (10, H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    vw.write(img)
vw.release()
cap.release()

subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(crudo),
                "-vcodec", "libx264", "-pix_fmt", "yuv420p", str(final)], check=True)
crudo.unlink(missing_ok=True)
print("Vídeo de revisión:", final)