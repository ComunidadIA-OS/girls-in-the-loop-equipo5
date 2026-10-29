"""Analiza en lote las ruedas de prensa del Consejo de Ministros publicadas en La Moncloa, sin intervención manual.
De cada página se toma:
  - el vídeo (HLS .m3u8), que se descarga con FFmpeg;
  - quién interviene y desde qué segundo («Intervenciones destacadas»), para asignar cada primer plano;
  - el cargo oficial («Ministra de…», «Ministro de…»), del que sale la categoría documentada. El género no se infiere de la imagen.
Cada vídeo entra en la cola como dos trabajos (visión y métricas) y se ve en la app como cualquier otro análisis.

Uso:
  python moncloa.py URL [URL ...]                  páginas concretas
  python moncloa.py --recientes                    las que aparecen en el índice de La Moncloa
  python moncloa.py --desde 2026-09-01 [--hasta 2026-10-31]
"""
import argparse, datetime as dt, json, re, shutil, subprocess, sys, time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent
FIR = RAIZ / "FIRDAOUS"
VISION = RAIZ / "PAULA" / "consejo_integrado"
VIDEOS = RAIZ / "videos"
sys.path.insert(0, str(RAIZ))
import cola  # noqa: E402

WEB = "https://www.lamoncloa.gob.es"
INDICE = f"{WEB}/consejodeministros/resumenes/Paginas/index.aspx"
CABECERA = {"User-Agent": "Mozilla/5.0 (girls-in-the-loop; analisis academico)"}
# Primera palabra con género gramatical en el cargo oficial → categoría documentada
CARGOS = {"ministra": "mujer", "ministro": "hombre", "vicepresidenta": "mujer", "vicepresidente": "hombre",
          "presidenta": "mujer", "presidente": "hombre", "secretaria": "mujer", "secretario": "hombre",
          "directora": "mujer", "director": "hombre", "delegada": "mujer", "delegado": "hombre"}


# ---------- Leer La Moncloa ----------
def descargar_html(url):
    for intento in range(4):            # la web a veces tarda; se reintenta antes de dar la página por perdida
        try:
            r = requests.get(url, headers=CABECERA, timeout=60)
            r.raise_for_status()
            break
        except requests.RequestException:
            if intento == 3:
                raise
            time.sleep(10 * (intento + 1))
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:          # algunas páginas declaran utf-8 pero vienen en Windows-1252
        return r.content.decode("cp1252", errors="replace")


def categoria(cargo):
    for palabra in re.findall(r"\w+", cargo.lower()):
        if palabra in CARGOS:
            return CARGOS[palabra]
    return "no_documentado"


def slug(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def leer_pagina(url):
    """Datos de una rueda de prensa: fecha, vídeo, personas (con cargo y categoría) y marcas de tiempo."""
    m = re.search(r"/(\d{2})(\d{2})(\d{2})-rueda-prensa", url)
    if not m:
        raise ValueError(f"No parece una página de rueda de prensa de La Moncloa: {url}")
    d, mes, a = m.groups()
    html = descargar_html(url)
    videos = sorted(set(re.findall(r"//smultimedia\.lamoncloa\.gob\.es/[^\"'\s<>]+?\.m3u8", html)))
    if not videos:
        raise ValueError(f"La página no tiene vídeo: {url}")
    sopa = BeautifulSoup(html, "html.parser")
    personas, marcas = [], []
    for bloque in sopa.select("li.itemInfo"):
        nombre = bloque.select_one(".itemName").get_text(strip=True)
        cargo = bloque.select_one(".itemPosition").get_text(strip=True) if bloque.select_one(".itemPosition") else ""
        personas.append({"nombre": nombre, "cargo": cargo, "categoria": categoria(cargo)})
        for a_ in bloque.select("a[onclick*=seleccionarIntervencion]"):
            s = re.search(r"seleccionarIntervencion\((\d+)\)", a_["onclick"])
            if s:
                marcas.append({"inicio_s": int(s.group(1)), "nombre": nombre})
    return {"url": url, "nombre": f"consejo_{d}{mes}{a}", "titulo": f"Consejo de Ministros {d}/{mes}/20{a}",
            "video_url": "https:" + videos[0], "personas": personas, "marcas": sorted(marcas, key=lambda x: x["inicio_s"])}


def paginas_recientes():
    html = descargar_html(INDICE)
    rutas = dict.fromkeys(re.findall(r"/consejodeministros/resumenes/Paginas/\d{4}/\d{6}-rueda-prensa-ministros\.aspx", html))
    return [WEB + r for r in rutas]


def paginas_entre(desde, hasta):
    """Prueba cada día del intervalo (el Consejo suele ser el martes, pero no siempre)."""
    urls, dia = [], desde
    while dia <= hasta:
        url = f"{WEB}/consejodeministros/resumenes/Paginas/{dia:%Y}/{dia:%d%m%y}-rueda-prensa-ministros.aspx"
        try:
            r = requests.get(url, headers=CABECERA, timeout=30)
            if r.ok and b"mediaItemInfoList" in r.content:
                urls.append(url)
                print("  encontrada:", url, flush=True)
        except requests.RequestException:
            pass
        dia += dt.timedelta(days=1)
        time.sleep(0.3)                 # sin saturar la web
    return urls


# ---------- Configs ----------
def configs_existentes():
    return {json.load(open(p, encoding="utf-8"))["nombre"]: p for p in sorted(FIR.glob("config_*.json"))}


def guardar(ruta, datos):
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def preparar(info):
    """Crea (o completa) los config de visión y de métricas. Devuelve las rutas."""
    nombre = info["nombre"]
    ids = {}
    for p in info["personas"]:
        ids.setdefault(p["nombre"], chr(ord("A") + len(ids)))
    grupos = [{"id": ids[p["nombre"]], "texto": "", "nombre": p["nombre"], "persona": slug(p["nombre"]),
               "categoria": p["categoria"], "cargo": p["cargo"]} for p in info["personas"]]
    marcas = [{"inicio_s": m["inicio_s"], "grupo": ids[m["nombre"]]} for m in info["marcas"]]

    ruta_m = configs_existentes().get(nombre, FIR / f"config_{nombre}.json")
    cfg = json.load(open(ruta_m, encoding="utf-8")) if Path(ruta_m).exists() else {}
    plantilla = json.load(open(FIR / "config_131026.json", encoding="utf-8"))
    gpu = shutil.which("nvidia-smi") is not None
    cfg = {"nombre": nombre, "titulo": info["titulo"], "video": f"videos/{nombre}.mp4",
           "resultados_vision": f"PAULA/consejo_integrado/resultados_{nombre}", "salida": f"FIRDAOUS/salidas/{nombre}",
           "excluir_planos": [], "umbrales": {**plantilla["umbrales"], "min_area_persona": 3},
           "modelo_whisper": "large-v3" if gpu else "medium", **cfg,
           "fuente": info["url"], "video_url": info["video_url"]}
    if not cfg.get("grupos"):           # no se pisa una revisión manual ya hecha
        cfg["grupos"] = grupos
    if not cfg.get("intervenciones") and {g["id"] for g in cfg["grupos"]} >= {m["grupo"] for m in marcas}:
        cfg["intervenciones"] = marcas
    guardar(ruta_m, cfg)

    ruta_v = VISION / f"config_{nombre}.json"
    if not ruta_v.exists():
        modelo = VISION / "modelos" / "yolo11m.pt"
        calidad = ({"muestras_s": 10, "imgsz": 960, "ocr_cada_s": 0.5} if gpu else
                   {"muestras_s": 2, "imgsz": 640, "ocr_cada_s": 2.0})
        # rutas relativas a la raíz del repositorio (la cola y las instrucciones se ejecutan desde ahí)
        guardar(ruta_v, {"video": cfg["video"], "salida": cfg["resultados_vision"],
                         "inicio_s": 0.0, "fin_s": None, **calidad, "exigir_gpu": gpu,
                         "modelo": str(modelo.relative_to(RAIZ)) if modelo.exists() else "yolo11m.pt", "conf_ocr": 0.6})
    return Path(ruta_m), ruta_v


def encolar(url):
    info = leer_pagina(url)
    ruta_m, ruta_v = preparar(info)
    cfg = json.load(open(ruta_m, encoding="utf-8"))
    R, out = RAIZ / cfg["resultados_vision"], RAIZ / cfg["salida"]
    personas = ", ".join(f"{p['nombre']} ({p['categoria']})" for p in info["personas"])
    if (out / "resumen.json").exists():
        print(f"= {info['titulo']}: ya analizada.")
        return f"{info['titulo']}: ya analizada."
    estado_v = json.load(open(R / "estado.json")).get("estado") if (R / "estado.json").exists() else None
    if estado_v != "completo":
        cola.encolar("vision", R, [sys.executable, Path(__file__).resolve(), "_vision", ruta_m, ruta_v])
    cola.encolar("metricas", out, [sys.executable, Path(__file__).resolve(), "_metricas", ruta_m])
    print(f"+ {info['titulo']}: en cola. {personas}")
    return f"{info['titulo']}: en cola. {personas}"


# ---------- Trabajos que ejecuta la cola ----------
def descargar_hls(url, destino):
    """Descarga un vídeo HLS trozo a trozo, comprobando que cada trozo llega entero (el servidor a veces corta
    la conexión a medias y FFmpeg lo pasa por alto, dejando huecos), y lo une en un MP4."""
    from urllib.parse import urljoin
    lista = descargar_html(url)
    variantes = [l for l in lista.splitlines() if l and not l.startswith("#")]
    if lista.count("#EXT-X-STREAM-INF"):            # lista maestra: elegir la variante (aquí solo hay una)
        url = urljoin(url, variantes[-1])
        variantes = [l for l in descargar_html(url).splitlines() if l and not l.startswith("#")]
    tmp = destino.with_suffix(".part.ts")
    with open(tmp, "wb") as salida:
        for n, trozo in enumerate(variantes, 1):
            for intento in range(6):
                try:
                    r = requests.get(urljoin(url, trozo), headers=CABECERA, timeout=60)
                    r.raise_for_status()
                    esperado = int(r.headers.get("Content-Length", len(r.content)))
                    if len(r.content) != esperado:
                        raise requests.RequestException(f"trozo incompleto ({len(r.content)} de {esperado} bytes)")
                    break
                except requests.RequestException as e:
                    if intento == 5:
                        raise RuntimeError(f"No se pudo descargar el trozo {n}: {e}")
                    time.sleep(3 * (intento + 1))
            salida.write(r.content)
            if n % 50 == 0 or n == len(variantes):
                print(f"  {n}/{len(variantes)} trozos", flush=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp), "-c", "copy",
                    "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", str(destino)], check=True)
    tmp.unlink()


def trabajo_vision(ruta_m, ruta_v):
    cfg = json.load(open(ruta_m, encoding="utf-8"))
    video = RAIZ / cfg["video"]
    if not video.exists():
        VIDEOS.mkdir(exist_ok=True)
        print(f"Descargando {cfg['video_url']} ...", flush=True)
        descargar_hls(cfg["video_url"], video)
    sys.exit(subprocess.run([sys.executable, "-u", str(RAIZ / "analizar_video.py"), str(ruta_v), str(ruta_m)]).returncode)


def trabajo_metricas(ruta_m):
    for fase in ("revisar", "metricas", "informe"):
        print(f"\n== {fase} ==", flush=True)
        r = subprocess.run([sys.executable, "-u", str(FIR / "pipeline.py"), str(ruta_m), fase])
        if r.returncode:
            sys.exit(r.returncode)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_vision":
        return trabajo_vision(*sys.argv[2:4])
    if len(sys.argv) > 1 and sys.argv[1] == "_metricas":
        return trabajo_metricas(sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--recientes", action="store_true")
    ap.add_argument("--desde", type=dt.date.fromisoformat)
    ap.add_argument("--hasta", type=dt.date.fromisoformat, default=dt.date.today())
    a = ap.parse_args()
    urls = list(a.urls)
    if a.recientes:
        urls += paginas_recientes()
    if a.desde:
        urls += paginas_entre(a.desde, a.hasta)
    if not urls:
        ap.error("indica URLs, --recientes o --desde")
    for url in dict.fromkeys(urls):
        try:
            encolar(url)
        except Exception as e:          # una página rara no detiene el lote
            print(f"! {url}: {e}")


if __name__ == "__main__":
    main()
