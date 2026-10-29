"""Cola de trabajos: ejecuta de uno en uno los análisis pesados (GPU) que encola la app.
La app lo arranca sola; no hace falta ejecutarlo a mano.
"""
import json, os, subprocess, sys, time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
COLA = RAIZ / "cola"
CERROJO = COLA / "trabajador.lock"


# ---------- Cerrojo: solo un trabajador a la vez ----------
def bloquear(f):
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def desbloquear(f):
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)


def activo():
    """¿Hay un trabajador ejecutando la cola?"""
    COLA.mkdir(exist_ok=True)
    with open(CERROJO, "a+") as f:
        if not bloquear(f):
            return True
        desbloquear(f)
        return False


# ---------- Uso desde la app ----------
def pendientes():
    return sorted(COLA.glob("*.json")) if COLA.exists() else []


def encolar(trabajo, carpeta, cmd):
    """Añade un trabajo. Deja carpeta/trabajo.cola mientras espera, .log mientras corre y .rc al acabar."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    COLA.mkdir(exist_ok=True)
    for ext in ("rc", "log"):
        (carpeta / f"{trabajo}.{ext}").unlink(missing_ok=True)
    (carpeta / f"{trabajo}.cola").write_text("")
    (COLA / f"{time.time_ns()}_{trabajo}.json").write_text(
        json.dumps({"trabajo": trabajo, "carpeta": str(carpeta), "cmd": [str(c) for c in cmd]}), encoding="utf-8")
    arrancar()


def posicion(trabajo, carpeta):
    """1 = el siguiente en ejecutarse."""
    for i, ruta in enumerate(pendientes(), start=1):
        t = json.loads(ruta.read_text(encoding="utf-8"))
        if t["trabajo"] == trabajo and Path(t["carpeta"]) == Path(carpeta):
            return i
    return None


def arrancar():
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, str(Path(__file__).resolve())], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)


# ---------- Trabajador ----------
def ejecutar(ruta):
    t = json.loads(ruta.read_text(encoding="utf-8"))
    carpeta = Path(t["carpeta"])
    (carpeta / f"{t['trabajo']}.cola").unlink(missing_ok=True)
    with open(carpeta / f"{t['trabajo']}.log", "w", encoding="utf-8") as log:
        r = subprocess.run(t["cmd"], stdout=log, stderr=subprocess.STDOUT, cwd=RAIZ,
                           env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    (carpeta / f"{t['trabajo']}.rc").write_text(str(r.returncode))
    ruta.unlink(missing_ok=True)


def main():
    COLA.mkdir(exist_ok=True)
    while True:
        with open(CERROJO, "a+") as f:
            if not bloquear(f):
                return                      # ya hay otro trabajador
            try:
                while pendientes():
                    ejecutar(pendientes()[0])
            finally:
                desbloquear(f)
        if not pendientes():                # si entró un trabajo justo al soltar el cerrojo, seguir
            return


if __name__ == "__main__":
    main()
