"""Girls in the Loop: interfaz del proyecto.
Uso: streamlit run app.py
"""
import importlib.util, json, os, re, shutil, subprocess, sys
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent
FIR = RAIZ / "FIRDAOUS"
VISION = RAIZ / "PAULA" / "consejo_integrado"
sys.path.insert(0, str(FIR))
import pipeline  # noqa: E402

st.set_page_config(page_title="Girls in the Loop", page_icon="🎙️", layout="wide")
CATEGORIAS = ["mujer", "hombre", "no_documentado"]
HAY_GPU = shutil.which("nvidia-smi") is not None
HAY_WHISPER = importlib.util.find_spec("faster_whisper") is not None
TINTA, TINTA_2 = "#0b0b0b", "#52514e"


# ---------- Configs y procesos ----------
def configs():
    return {json.load(open(p, encoding="utf-8"))["nombre"]: p for p in sorted(FIR.glob("config_*.json"))}


def leer(ruta):
    return json.load(open(ruta, encoding="utf-8"))


def guardar(ruta, cfg):
    Path(ruta).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def config_vision(cfg):
    propio = VISION / f"config_{cfg['nombre']}.json"
    return propio if propio.exists() else VISION / "config.json"


def lanzar(trabajo, carpeta, cmd):
    """Ejecuta cmd en segundo plano; deja trabajo.log y, al acabar, trabajo.rc con el código de salida."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{trabajo}.rc").unlink(missing_ok=True)
    envoltorio = "import subprocess,sys; r=subprocess.run(sys.argv[2:]); open(sys.argv[1],'w').write(str(r.returncode))"
    entorno = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, "-c", envoltorio, str(carpeta / f"{trabajo}.rc"), *map(str, cmd)],
                     stdout=open(carpeta / f"{trabajo}.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                     cwd=RAIZ, env=entorno, **extra)


def estado(trabajo, carpeta):
    rc, log = Path(carpeta) / f"{trabajo}.rc", Path(carpeta) / f"{trabajo}.log"
    if rc.exists():
        return "ok" if rc.read_text().strip() == "0" else "error"
    return "en_curso" if log.exists() else "pendiente"


def ver_log(trabajo, carpeta, lineas=25):
    log = Path(carpeta) / f"{trabajo}.log"
    if log.exists():
        st.code("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lineas:]) or "(sin salida aún)")


def ejecutar_fase(ruta_cfg, fase):
    """Fases rápidas (revisar, informe): se ejecutan al momento y se muestra su salida."""
    r = subprocess.run([sys.executable, str(FIR / "pipeline.py"), str(ruta_cfg), fase], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    (st.success if r.returncode == 0 else st.error)(f"Fase «{fase}» {'completada' if r.returncode == 0 else 'con error'}")
    st.code((r.stdout + r.stderr).strip()[-3000:] or "(sin salida)")


def slug(texto):
    texto = texto.lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


ICONO = {"ok": "✅", "error": "❌", "en_curso": "⏳", "pendiente": "⚪"}


# ---------- Datos de resultados ----------
def nombres_personas(cfg):
    return {g["persona"]: g.get("nombre") or g["persona"].replace("_", " ").title() for g in cfg["grupos"] if g.get("persona")}


def etiqueta(k, nombres):
    return nombres.get(k, {"sala": "Sala de prensa", "sin_atribuir": "Sin atribuir"}.get(k, k))


def tema(fig, alto):
    fig.update_layout(height=alto, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(size=13),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig


def grafico_paridad(gen):
    fig = go.Figure()
    filas = {"pct_personas": "Personas portavoces", "pct_pantalla": "Tiempo en pantalla", "pct_habla": "Tiempo de voz"}
    for cat in gen.index:
        v = gen.loc[cat, list(filas)]
        fig.add_bar(y=list(filas.values()), x=v, name=cat, orientation="h",
                    marker=dict(color=pipeline.COLOR_GENERO.get(cat, "#8a8984"), line=dict(color="white", width=2)),
                    text=[f"{cat} {x:.0f} %" for x in v], textposition="inside", insidetextanchor="middle",
                    hovertemplate=f"{cat}: %{{x:.1f}} %<extra></extra>")
    fig.update_layout(barmode="stack")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, 100], title="% del total")
    return tema(fig, 280)


def grafico_linea_tiempo(pl, cfg, nombres, color, primera):
    persona_de = {g["id"]: g["persona"] for g in cfg["grupos"]}
    pl = pl[pl["tipo"] != "excluir"].copy()
    pl["clave"] = [persona_de.get(g) or ("sala" if t == "plano_medio" else "plano_general")
                   for g, t in zip(pl["grupo"], pl["tipo"])]
    fig = go.Figure()
    for clave in [*nombres, "sala", "plano_general"]:
        d = pl[pl["clave"] == clave]
        if d.empty:
            continue
        fig.add_bar(y=["emisión"] * len(d), x=d["dur_s"] / 60, base=d["inicio_s"] / 60, orientation="h",
                    name=etiqueta(clave, nombres) if clave != "plano_general" else "Plano general",
                    marker_color=color.get(clave) or pipeline.GRIS[clave],
                    customdata=d[["plano", "inicio_s", "dur_s"]],
                    hovertemplate="%{fullData.name}<br>plano %{customdata[0]} · min %{base:.1f}"
                                  "<br>%{customdata[2]:.0f} s<extra></extra>")
    if primera:
        fig.add_vline(x=primera / 60, line_dash="dash", line_color=TINTA_2, line_width=1,
                      annotation_text="turno de preguntas →", annotation_position="top right")
    fig.update_layout(barmode="overlay", bargap=0.2)
    fig.update_yaxes(visible=False)
    fig.update_xaxes(title="minuto de la emisión")
    return tema(fig, 230)


def grafico_voz(habla, nombres, color):
    h = habla.sort_values("pct_habla")
    fig = go.Figure(go.Bar(y=[etiqueta(k, nombres) for k in h.index], x=h["pct_habla"], orientation="h",
                           marker_color=[color.get(k) or pipeline.GRIS.get(k, "#8a8984") for k in h.index],
                           text=[f"{v:.1f} %" for v in h["pct_habla"]], textposition="outside",
                           customdata=h[["palabras", "tiempo_habla_s"]],
                           hovertemplate="%{y}: %{x:.1f} %<br>%{customdata[0]} palabras · "
                                         "%{customdata[1]:.0f} s<extra></extra>"))
    fig.update_xaxes(title="% del tiempo de voz transcrito", range=[0, h["pct_habla"].max() * 1.2])
    return tema(fig, 300)


def turnos(pal, nombres):
    pal = pal[pal["hablante"] != "excluir"].copy()
    pal["turno"] = (pal["hablante"] != pal["hablante"].shift()).cumsum()
    t = pal.groupby("turno").agg(inicio_s=("inicio_s", "min"), fin_s=("fin_s", "max"),
                                 hablante=("hablante", "first"), texto=("palabra", " ".join))
    t["minuto"] = (t["inicio_s"] / 60).round(1)
    t["hablante"] = t["hablante"].map(lambda k: etiqueta(k, nombres))
    return t[["minuto", "hablante", "texto"]]


# ---------- Pestaña: resultados ----------
def pestana_resultados(cfg):
    out = Path(cfg["salida"])
    if not (out / "resumen.json").exists():
        st.info("Este análisis aún no tiene métricas. Complétalo en la pestaña **Nuevo análisis / continuar**.")
        return
    res = leer(out / "resumen.json")
    gen = pd.read_csv(out / "metricas_genero.csv", index_col=0)
    habla = pd.read_csv(out / "metricas_habla.csv", index_col=0)
    per = pd.read_csv(out / "metricas_personas.csv")
    estr = pd.read_csv(out / "metricas_estructura.csv", index_col=0)
    fases = pd.read_csv(out / "metricas_fases.csv", index_col=0).reindex(columns=["exposicion", "preguntas"], fill_value=0)
    pl = pd.read_csv(out / "planos_clasificados.csv", keep_default_na=False)
    nombres = nombres_personas(cfg)
    color = pipeline.colores_personas(nombres)

    st.caption(f"Fuente: {cfg['fuente']}")
    c = st.columns(5)
    c[0].metric("Emisión útil", f"{res['emision_util_s'] / 60:.1f} min")
    for i, (m, txt) in enumerate([("pantalla", "Paridad pantalla"), ("habla", "Paridad voz")], start=1):
        if "mujer" in gen.index:
            c[i].metric(f"{txt} · mujeres", f"{gen.loc['mujer', f'paridad_{m}']:.2f}",
                        help="% obtenido / % de personas. 1 = proporcional; >1 = sobrerrepresentación")
    c[3].metric("Abre / cierra", f"{etiqueta(res['abre'], nombres).split()[0]} / {etiqueta(res['cierra'], nombres).split()[0]}")
    c[4].metric("Voz sin atribuir", f"{res['pct_habla_sin_atribuir']} %")

    st.subheader("¿Es proporcional el protagonismo?")
    st.plotly_chart(grafico_paridad(gen), use_container_width=True)
    st.subheader("Quién ocupa la pantalla, minuto a minuto")
    st.plotly_chart(grafico_linea_tiempo(pl, cfg, nombres, color, res["primera_pregunta_s"]), use_container_width=True)

    izq, der = st.columns(2)
    with izq:
        st.subheader("Reparto de la voz")
        st.plotly_chart(grafico_voz(habla, nombres, color), use_container_width=True)
    with der:
        st.subheader("Por persona")
        tabla = per.merge(estr, left_on="persona", right_index=True).merge(fases, left_on="persona", right_index=True)
        tabla["persona"] = tabla["persona"].map(nombres)
        st.dataframe(tabla[["persona", "categoria", "tiempo_pantalla_s", "tiempo_habla_s", "palabras",
                            "intervenciones", "duracion_media_s", "exposicion", "preguntas"]].round(1),
                     hide_index=True, use_container_width=True,
                     column_config={"tiempo_pantalla_s": "pantalla (s)", "tiempo_habla_s": "voz (s)",
                                    "duracion_media_s": "media interv. (s)", "exposicion": "exposición (s)",
                                    "preguntas": "preguntas (s)"})
        st.markdown("**Por género**")
        st.dataframe(gen.round(2), use_container_width=True)

    st.subheader("Transcripción por turnos")
    pal_ruta = out / "palabras_atribuidas.csv"
    if pal_ruta.exists():
        t = turnos(pd.read_csv(pal_ruta, keep_default_na=False), nombres)
        f1, f2 = st.columns([1, 2])
        quien = f1.multiselect("Hablante", sorted(t["hablante"].unique()))
        buscar = f2.text_input("Buscar en el texto")
        if quien:
            t = t[t["hablante"].isin(quien)]
        if buscar:
            t = t[t["texto"].str.contains(buscar, case=False, regex=False)]
        st.dataframe(t, hide_index=True, use_container_width=True, height=320,
                     column_config={"texto": st.column_config.TextColumn(width="large")})

    st.subheader("Descargas")
    d = st.columns(4)
    for col, f in zip(d, ["informe.md", "metricas_personas.csv", "metricas_genero.csv", "palabras_atribuidas.csv"]):
        if (out / f).exists():
            col.download_button(f, (out / f).read_bytes(), file_name=f"{cfg['nombre']}_{f}")


# ---------- Pestaña: comparar ----------
def pestana_comparar():
    filas = []
    for nombre, ruta in configs().items():
        cfg = pipeline.cargar_config(ruta)
        f = Path(cfg["salida"]) / "metricas_genero.csv"
        if f.exists():
            filas.append(pd.read_csv(f).assign(video=nombre))
    if len(filas) < 2:
        st.info("Hace falta analizar al menos dos ruedas de prensa para comparar. "
                f"Ahora hay {len(filas)} con métricas.")
        if not filas:
            return
    df = pd.concat(filas)
    fig = go.Figure()
    for cat in df["categoria"].unique():
        d = df[df["categoria"] == cat]
        fig.add_bar(x=d["video"], y=d["paridad_habla"], name=cat, marker_color=pipeline.COLOR_GENERO.get(cat, "#8a8984"),
                    hovertemplate=f"{cat} · %{{x}}<br>paridad voz %{{y:.2f}}<extra></extra>")
    fig.add_hline(y=1, line_dash="dash", line_color=TINTA_2, annotation_text="proporcional")
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="índice de paridad de voz")
    st.plotly_chart(tema(fig, 360), use_container_width=True)
    st.dataframe(df[["video", "categoria", "personas", "pct_personas", "pct_pantalla", "paridad_pantalla",
                     "pct_habla", "paridad_habla"]].round(2), hide_index=True, use_container_width=True)


# ---------- Pestaña: nuevo análisis / continuar ----------
def formulario_nuevo():
    with st.form("nuevo"):
        st.markdown("**Crear un análisis nuevo**")
        nombre = st.text_input("Nombre corto", placeholder="consejo_201026")
        video = st.text_input("Ruta del vídeo (absoluta o relativa a la carpeta equipo5)", placeholder="NOA/consejo_201026.mp4")
        fuente = st.text_input("Fuente pública que documenta quién comparece", placeholder="https://www.lamoncloa.gob.es/...")
        whisper = st.selectbox("Modelo de transcripción", ["large-v3", "medium", "small"],
                               help="large-v3 es el más preciso; en CPU usa small o medium")
        if not st.form_submit_button("Crear"):
            return
    nombre = slug(nombre)
    if not nombre or not video or not fuente:
        st.error("Rellena nombre, vídeo y fuente.")
        return
    if (FIR / f"config_{nombre}.json").exists():
        st.error("Ya existe un análisis con ese nombre.")
        return
    if not (RAIZ / video).exists():
        st.warning("No encuentro el vídeo en esta máquina. Se crea el análisis igualmente (la visión fallará hasta que exista).")
    base = leer(VISION / "config.json") if (VISION / "config.json").exists() else {}
    modelo = VISION / "modelos" / "yolo11m.pt"
    guardar(VISION / f"config_{nombre}.json", {
        **{"inicio_s": 0.0, "fin_s": None, "muestras_s": 10, "imgsz": 960, "exigir_gpu": True,
           "ocr_cada_s": 0.5, "conf_ocr": 0.6}, **{k: v for k, v in base.items() if k not in ("video", "salida", "modelo")},
        "video": str((RAIZ / video).resolve()), "salida": str(VISION / f"resultados_{nombre}"),
        "modelo": str(modelo) if modelo.exists() else "yolo11m.pt"})
    plantilla = leer(FIR / "config_131026.json")
    guardar(FIR / f"config_{nombre}.json", {
        "nombre": nombre, "video": video, "resultados_vision": f"PAULA/consejo_integrado/resultados_{nombre}",
        "salida": f"FIRDAOUS/salidas/{nombre}", "fuente": fuente, "excluir_planos": [],
        "umbrales": plantilla["umbrales"], "modelo_whisper": whisper, "grupos": []})
    st.session_state["analisis"] = nombre
    st.rerun()


def sugerir_rotulos(pl):
    """Textos OCR típicos de los primeros planos que no aparecen en planos generales (candidatos a nombre)."""
    def trozos(s):
        return {t.strip() for t in re.split(r"\|\|?", s) if len(t.strip()) >= 3}
    genericos = set().union(*map(trozos, pl.loc[pl["tipo"] != "primer_plano", "rotulos"]), set())
    cuenta = Counter()
    for _, p in pl[pl["tipo"] == "primer_plano"].iterrows():
        for t in trozos(p["rotulos"]) - genericos:
            cuenta[t] += p["dur_s"]
    return pd.DataFrame(cuenta.most_common(12), columns=["texto_ocr", "segundos_en_pantalla"]).round(0)


def pestana_proceso(nombre, ruta):
    cfg_crudo = leer(ruta)
    cfg = pipeline.cargar_config(ruta)
    out, R = Path(cfg["salida"]), Path(cfg["resultados_vision"])
    vcfg = config_vision(cfg)

    # Paso 1: visión
    estado_v = (leer(R / "estado.json").get("estado") if (R / "estado.json").exists() else None)
    hecho_v = estado_v == "completo"
    with st.expander(f"{'✅' if hecho_v else ICONO[estado('vision', R)]} 1 · Visión: planos, personas y rótulos (GPU)",
                     expanded=not hecho_v):
        st.caption(f"Config de visión: `{vcfg.relative_to(RAIZ)}` · resultados en `{R.relative_to(RAIZ)}`")
        if hecho_v:
            st.success("Visión completada.")
        if not HAY_GPU:
            st.warning("Esta máquina no tiene GPU NVIDIA: lanza la visión desde la VM de OVHcloud.")
        if st.button("Lanzar visión" if not hecho_v else "Relanzar (reanuda planos pendientes)", key="v",
                     disabled=not HAY_GPU):
            lanzar("vision", R, [sys.executable, VISION / "preparar_y_ejecutar.py", vcfg])
            st.rerun()
        if estado_v and estado_v != "completo":
            st.write("Estado del motor:", leer(R / "estado.json"))
        ver_log("vision", R)

    # Paso 2: grupos de rótulos → personas
    with st.expander(f"{'✅' if cfg['grupos'] and all(g.get('persona') and g.get('categoria') for g in cfg['grupos']) else '⚪'}"
                     " 2 · Revisión humana: quién es quién", expanded=hecho_v and not (out / "resumen.json").exists()):
        if not (R / "planos.csv").exists():
            st.info("Primero completa la visión.")
        else:
            if st.button("Clasificar planos (revisar)"):
                ejecutar_fase(ruta, "revisar")
            if (out / "planos_clasificados.csv").exists():
                pl = pd.read_csv(out / "planos_clasificados.csv", keep_default_na=False)
                st.markdown("Cada **grupo** une los primeros planos cuyo rótulo OCR contiene un texto. "
                            "Se comprueban en orden; un texto vacío recoge lo que quede, así que va el último. "
                            "La categoría se toma de la fuente pública, **nunca de la imagen**.")
                a, b = st.columns([1, 1])
                a.markdown("Textos candidatos (rótulos de primeros planos)")
                a.dataframe(sugerir_rotulos(pl), hide_index=True, use_container_width=True)
                b.markdown("Primeros planos")
                b.dataframe(pl.loc[pl["tipo"] == "primer_plano", ["plano", "inicio_s", "dur_s", "grupo", "rotulos"]].round(1),
                            hide_index=True, use_container_width=True, height=250)
                grupos = pd.DataFrame(cfg_crudo["grupos"], columns=["id", "texto", "nombre", "persona", "categoria"])
                editado = st.data_editor(grupos, num_rows="dynamic", use_container_width=True, key="grupos",
                                         column_config={"categoria": st.column_config.SelectboxColumn(options=CATEGORIAS),
                                                        "persona": st.column_config.TextColumn(help="Se rellena solo a partir del nombre")})
                excluir = st.multiselect("Planos a excluir (cabeceras, rótulos, vídeos insertados)",
                                         pl["plano"].tolist(), default=cfg_crudo["excluir_planos"])
                if st.button("Guardar grupos y reclasificar", type="primary"):
                    filas = editado.fillna("").astype(str).to_dict("records")
                    for i, g in enumerate(filas):
                        g["id"] = g["id"] or chr(65 + i)
                        g["persona"] = g["persona"] or slug(g["nombre"])
                    cfg_crudo.update(grupos=[g for g in filas if g["persona"] or g["texto"]], excluir_planos=excluir)
                    guardar(ruta, cfg_crudo)
                    ejecutar_fase(ruta, "revisar")
                carpetas = sorted((out / "revision").glob("primer_plano*")) if (out / "revision").exists() else []
                for carpeta in carpetas:
                    st.markdown(f"**{carpeta.name}**")
                    imgs = sorted(carpeta.glob("*.jpg"))[:8]
                    st.image([str(i) for i in imgs], caption=[i.stem for i in imgs], width=120)
                if not carpetas:
                    st.caption("Sin imágenes de revisión en esta máquina (los recortes están en la VM).")

    # Paso 3: métricas
    listo_grupos = bool(cfg["grupos"]) and all(g.get("persona") and g.get("categoria") for g in cfg["grupos"])
    hecho_m = (out / "resumen.json").exists()
    with st.expander(f"{'✅' if hecho_m else ICONO[estado('metricas', out)]} 3 · Transcripción y métricas",
                     expanded=listo_grupos and not hecho_m):
        sin_whisper = not HAY_WHISPER and not (out / "transcripcion_palabras.csv").exists()
        if sin_whisper:
            st.warning("Falta faster-whisper en esta máquina (pip install faster-whisper) y aún no hay transcripción.")
        if not listo_grupos:
            st.info("Completa persona y categoría de todos los grupos.")
        elif st.button("Calcular métricas" if not hecho_m else "Recalcular (reutiliza la transcripción)", key="m",
                       disabled=sin_whisper):
            lanzar("metricas", out, [sys.executable, FIR / "pipeline.py", ruta, "metricas"])
            st.rerun()
        if not (out / "transcripcion_palabras.csv").exists():
            st.caption("La primera vez transcribe el audio con Whisper: en GPU tarda minutos; en CPU, horas.")
        ver_log("metricas", out)

    # Paso 4: informe
    with st.expander(f"{'✅' if (out / 'informe.md').exists() else '⚪'} 4 · Informe (gráficos PNG + Markdown)"):
        if not hecho_m:
            st.info("Primero calcula las métricas.")
        elif st.button("Generar informe"):
            ejecutar_fase(ruta, "informe")

    if st.button("🔄 Actualizar estado"):
        st.rerun()


# ---------- Página ----------
with st.sidebar:
    st.title("Girls in the Loop")
    st.caption("Protagonismo por género en ruedas de prensa · Equipo 5")
    lista = configs()
    if not lista:
        st.stop()
    nombres_cfg = list(lista)
    elegido = st.selectbox("Rueda de prensa", nombres_cfg,
                           index=nombres_cfg.index(st.session_state.get("analisis", nombres_cfg[0]))
                           if st.session_state.get("analisis") in nombres_cfg else 0)
    st.session_state["analisis"] = elegido
    st.divider()
    st.markdown("**Entorno de esta máquina**")
    for ok, txt in [(shutil.which("ffmpeg") is not None, "FFmpeg"), (HAY_GPU, "GPU NVIDIA"), (HAY_WHISPER, "faster-whisper")]:
        st.markdown(f"{'✅' if ok else '⚠️'} {txt}")
    if not HAY_GPU:
        st.caption("Sin GPU puedes ver resultados; para analizar vídeos nuevos usa la VM de OVHcloud.")

cfg_sel = pipeline.cargar_config(lista[elegido])
st.header(cfg_sel.get("nombre", elegido))
t1, t2, t3 = st.tabs(["📊 Resultados", "⚙️ Nuevo análisis / continuar", "⚖️ Comparar"])
with t1:
    pestana_resultados(cfg_sel)
with t2:
    formulario_nuevo()
    st.divider()
    st.markdown(f"**Pasos de «{elegido}»**")
    pestana_proceso(elegido, lista[elegido])
with t3:
    pestana_comparar()
