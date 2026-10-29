"""Prepara cualquier vídeo para el motor de visión y lo lanza.
Si el vídeo no pasa la validación del motor (tiempos desordenados, frecuencia variable,
formato que OpenCV no lee), lo recodifica a MP4 H.264 a 25 fps constantes (<vídeo>_norm.mp4)
y actualiza los config. La app lo encola como trabajo «vision».
Uso: python analizar_video.py CONFIG_VISION.json [CONFIG_METRICAS.json]
"""
import json, shutil, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VISION = RAIZ / "PAULA" / "consejo_integrado"
sys.path.insert(0, str(VISION))


def problema(video):
    """None si el motor de visión puede leer el vídeo tal cual; si no, el motivo."""
    import cv2
    from analizar_consejo import frame_times
    cap = cv2.VideoCapture(str(video))
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if not fps or fps <= 0 or total <= 0:
        return "OpenCV no puede leer el vídeo"
    try:
        frame_times(video, fps, total)
    except (RuntimeError, ValueError, KeyError) as e:
        return str(e)
    return None


def normalizar(video):
    destino = video.with_name(f"{video.stem}_norm.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-fflags", "+genpts", "-i", str(video),
                    "-vf", "fps=25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(destino)], check=True)
    return destino


def main(ruta_vision, ruta_metricas=None):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("Falta FFmpeg (ffmpeg y ffprobe) en esta máquina.")
    cfg = json.loads(Path(ruta_vision).read_text(encoding="utf-8"))
    video = Path(cfg["video"])
    if not video.is_file():
        sys.exit(f"No existe el vídeo: {video}")

    print("Comprobando el vídeo...", flush=True)
    motivo = problema(video)
    if motivo:
        print(f"El vídeo necesita normalizarse ({motivo}). Recodificando a 25 fps; tarda unos minutos...", flush=True)
        video = normalizar(video)
        if problema(video):
            sys.exit(f"Ni siquiera el vídeo normalizado es válido: {problema(video)}")
        cfg["video"] = str(video)
        Path(ruta_vision).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        if ruta_metricas:   # la transcripción usa el mismo vídeo, para que audio e imagen compartan tiempos
            m = json.loads(Path(ruta_metricas).read_text(encoding="utf-8"))
            m["video"] = str(video.relative_to(RAIZ)) if video.is_relative_to(RAIZ) else str(video)
            Path(ruta_metricas).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Vídeo normalizado: {video.name}", flush=True)
    else:
        print("Vídeo válido; no hace falta normalizar.", flush=True)

    r = subprocess.run([sys.executable, "-u", str(VISION / "preparar_y_ejecutar.py"), str(ruta_vision)])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main(*sys.argv[1:3])
