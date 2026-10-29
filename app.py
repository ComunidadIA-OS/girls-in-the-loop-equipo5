"""Girls in the Loop: interfaz del proyecto.
Uso: streamlit run app.py
"""
import base64, importlib.util, json, os, random, re, secrets, shutil, subprocess, sys
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent
FIR = RAIZ / "FIRDAOUS"
VISION = RAIZ / "PAULA" / "consejo_integrado"
VIDEOS = RAIZ / "videos"
sys.path.insert(0, str(FIR))
import pipeline  # noqa: E402
import cola  # noqa: E402
import moncloa  # noqa: E402

ASSETS = RAIZ / "assets"
st.set_page_config(page_title="Girls in the Loop", page_icon=str(ASSETS / "avatares" / "avatar_01.png"), layout="wide")
CATEGORIAS = ["mujer", "hombre", "no_documentado"]
HAY_GPU = shutil.which("nvidia-smi") is not None
HAY_WHISPER = importlib.util.find_spec("faster_whisper") is not None

# ---------- Estética ----------
# Paletas validadas con el validador de dataviz (luminosidad, croma, daltonismo y contraste: todo PASS)
TINTA, TINTA_2, TINTA_3 = "#24163f", "#5b4d7a", "#8a7fa3"
COLOR_GENERO = {"mujer": "#6d28d9", "hombre": "#0e8f86", "no_documentado": "#9a93ab"}
COLOR_PERSONA = ["#6d28d9", "#e0457b", "#c27c0e", "#0e8f86", "#3b6fe0", "#a3367a"]
GRIS = {"sala": "#8e86a3", "sin_atribuir": "#cdc6da", "plano_general": "#e9e4f3"}
NOMBRE_CATEGORIA = {"mujer": "Mujeres", "hombre": "Hombres", "no_documentado": "No documentado"}
AVATARES = sorted((ASSETS / "avatares").glob("avatar_*.png"))
AVATARES_GRANDES = sorted((ASSETS / "avatares").glob("grande_*.png"))


@st.cache_data
def b64(ruta):
    ruta = Path(ruta)
    tipo = "png" if ruta.suffix == ".png" else "jpeg"
    return f"data:image/{tipo};base64,{base64.b64encode(ruta.read_bytes()).decode()}"


def avatares(n, grandes=False):
    """Avatares distintos en cada recarga: la interfaz «cambia de cara» al navegar."""
    lista = AVATARES_GRANDES if grandes else AVATARES
    return random.sample(lista, min(n, len(lista)))


def html(codigo):
    st.markdown(codigo, unsafe_allow_html=True)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@500;600;700&display=swap');
:root { --morado-950:#1a0d33; --morado-900:#24123f; --morado-700:#4c1d95; --morado-600:#6d28d9;
        --morado-400:#a78bfa; --lavanda-200:#e3d9f5; --lavanda-100:#f3eefc; --tinta:#24163f; --tinta-2:#5b4d7a; }
h1, h2, h3, h4, .pixel { font-family: 'Pixelify Sans', 'Inter', sans-serif !important; letter-spacing: .01em; }
.block-container { padding-top: 3.2rem; max-width: 1320px; }
[data-testid="stSidebar"] img { image-rendering: auto; }
img.px { image-rendering: pixelated; }

/* Cabecera */
.hero { display:flex; align-items:center; justify-content:space-between; gap:24px; flex-wrap:nowrap;
        overflow:hidden;
        background: linear-gradient(120deg, #ffffff 0%, #f1e9ff 60%, #e6d8ff 100%);
        border:1px solid var(--lavanda-200); border-radius:22px; padding:22px 28px; margin-bottom:14px; }
.hero > div:first-child { flex:1 1 380px; } .hero .tira { flex:0 1 auto; }
.hero .logo { height:74px; }
.hero p { margin:.5rem 0 0; color:var(--tinta-2); max-width:470px; font-size:1rem; }
.hero .chip { display:inline-block; margin-top:.7rem; padding:.3rem .8rem; border-radius:999px;
              background:var(--morado-600); color:#fff; font-weight:600; font-size:.85rem; }
.hero .chip.priv { background:#fff; color:var(--morado-600); border:1px solid var(--morado-400); margin-left:.4rem; }
.tira { display:flex; align-items:flex-end; gap:6px; }
.tira img { height:88px; animation: flota 3.2s ease-in-out infinite; filter: drop-shadow(0 4px 6px rgba(76,29,149,.18)); }
.tira img:nth-child(2) { animation-delay:.4s } .tira img:nth-child(3) { animation-delay:.8s }
.tira img:nth-child(4) { animation-delay:1.2s } .tira img:nth-child(5) { animation-delay:1.6s }
@media (max-width: 1000px) { .hero { flex-wrap:wrap; } .tira img { height:64px; } }
@keyframes flota { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-7px) } }

/* Pestañas como píldoras */
[role="tablist"] { gap:6px; background:#fff; padding:6px; border-radius:14px; border:1px solid var(--lavanda-200);
                   width:fit-content; max-width:100%; flex-wrap:wrap; }
[data-testid="stTab"] { border-radius:10px; padding:8px 18px !important; }
[data-testid="stTab"] p { font-weight:600; color:var(--tinta-2); font-size:1rem; }
[data-testid="stTab"][aria-selected="true"] { background:var(--morado-600); }
[data-testid="stTab"][aria-selected="true"] p { color:#fff; }
[role="tablist"] .react-aria-SelectionIndicator { display:none; }

/* Tarjetas */
[data-testid="stVerticalBlockBorderWrapper"] { background:#fff; border-radius:18px !important; }
.titulo-seccion { display:flex; align-items:center; gap:12px; margin:.4rem 0 .6rem; }
.titulo-seccion img { height:54px; }
.titulo-seccion .tt { font-family:'Pixelify Sans', sans-serif; font-weight:600; font-size:1.5rem; color:var(--tinta); line-height:1.2; }
.titulo-seccion .ts { color:var(--tinta-2); font-size:.92rem; }
.kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:.3rem 0 1rem; }
.kpi { position:relative; background:#fff; border:1px solid var(--lavanda-200); border-radius:18px; padding:14px 16px 12px;
       min-height:132px; padding-bottom:64px; overflow:hidden; }
.kpi .et { color:var(--tinta-2); font-size:.85rem; font-weight:600; }
.kpi .val { font-family:'Pixelify Sans', sans-serif; font-size:2.3rem; color:var(--tinta); line-height:1.15; margin-top:.25rem; }
.kpi .sub { color:var(--tinta-2); font-size:.78rem; max-width:64%; }
.kpi img { position:absolute; right:6px; bottom:0; height:62px; }
.nota { background:var(--lavanda-100); border-left:4px solid var(--morado-600); border-radius:10px; padding:.7rem 1rem;
        color:var(--tinta); font-size:.92rem; margin:.4rem 0 .8rem; }

/* Cómo funciona */
.pasos { display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap:12px; }
.paso { background:#fff; border:1px solid var(--lavanda-200); border-radius:18px; padding:16px; }
.paso .n { display:inline-flex; width:30px; height:30px; border-radius:50%; background:var(--morado-600); color:#fff;
           align-items:center; justify-content:center; font-weight:700; margin-right:8px; }
.paso b { color:var(--tinta); } .paso p { color:var(--tinta-2); font-size:.9rem; margin:.5rem 0 0; }
.paso img { height:70px; display:block; margin:0 auto 6px; }

/* Pie con entidades */
.pie { margin-top:2.2rem; background:#fff; border:1px solid var(--lavanda-200); border-radius:18px; padding:16px 22px; }
.pie .fila { display:flex; align-items:center; justify-content:center; gap:28px; flex-wrap:wrap; }
.pie .fila img { height:60px; object-fit:contain; }
.pie small { display:block; text-align:center; color:var(--tinta-2); margin-top:10px; }
</style>
"""


# ---------- Configs y procesos ----------
def configs():
    return {json.load(open(p, encoding="utf-8"))["nombre"]: p for p in sorted(FIR.glob("config_*.json"))}


def leer(ruta):
    return json.load(open(ruta, encoding="utf-8"))


# ---------- Análisis privados: cada uno tiene un código; se ve solo con el enlace ?a=CÓDIGO ----------
def mis_codigos():
    return [c for c in st.query_params.get("a", "").split(",") if c]


def recordar_codigo(codigo):
    st.query_params["a"] = ",".join(dict.fromkeys(mis_codigos() + [codigo]))


def visibles():
    """Análisis sin código (públicos, p. ej. el del 13/10) + los de los códigos de este enlace."""
    return {n: p for n, p in configs().items() if not leer(p).get("codigo") or leer(p)["codigo"] in mis_codigos()}


def guardar(ruta, cfg):
    Path(ruta).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def config_vision(cfg):
    propio = VISION / f"config_{cfg['nombre']}.json"
    return propio if propio.exists() else VISION / "config.json"


def estado(trabajo, carpeta):
    rc, log = Path(carpeta) / f"{trabajo}.rc", Path(carpeta) / f"{trabajo}.log"
    if rc.exists():
        return "ok" if rc.read_text().strip() == "0" else "error"
    if (Path(carpeta) / f"{trabajo}.cola").exists():
        return "en_cola"
    return "en_curso" if log.exists() else "pendiente"


def ver_log(trabajo, carpeta, lineas=25):
    if estado(trabajo, carpeta) == "en_cola":
        pos = cola.posicion(trabajo, carpeta)
        st.info(f"🕒 En cola: {pos - 1 if pos else '?'} trabajo(s) por delante. Empezará solo cuando terminen; "
                "puedes cerrar la página y volver con tu enlace.")
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


ICONO = {"ok": "✅", "error": "❌", "en_curso": "⏳", "en_cola": "🕒", "pendiente": "⚪"}


# ---------- Datos de resultados ----------
def nombres_personas(cfg):
    return {g["persona"]: g.get("nombre") or g["persona"].replace("_", " ").title() for g in cfg["grupos"] if g.get("persona")}


def etiqueta(k, nombres):
    return nombres.get(k, {"sala": "Sala de prensa", "sin_atribuir": "Sin atribuir"}.get(k, k))


def colores_personas(nombres):
    return {p: COLOR_PERSONA[i] if i < len(COLOR_PERSONA) else TINTA_3 for i, p in enumerate(nombres)}


def tema(fig, alto):
    fig.update_layout(height=alto, margin=dict(l=8, r=8, t=36, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", size=13, color=TINTA),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(color=TINTA_2)),
                      hoverlabel=dict(bgcolor="#fff", bordercolor="#e3d9f5", font=dict(family="Inter", color=TINTA)),
                      barcornerradius=4)
    fig.update_xaxes(gridcolor="rgba(109,40,217,0.08)", zeroline=False, linecolor="#e3d9f5",
                     tickfont=dict(color=TINTA_2), title_font=dict(color=TINTA_2))
    fig.update_yaxes(gridcolor="rgba(109,40,217,0.08)", zeroline=False, tickfont=dict(color=TINTA_2),
                     title_font=dict(color=TINTA_2))
    return fig


def titulo_seccion(texto, sub="", avatar=None):
    img = f'<img class="px" src="{b64(avatar)}" alt="">' if avatar else ""
    html(f'<div class="titulo-seccion">{img}<div><div class="tt">{texto}</div><div class="ts">{sub}</div></div></div>')


def grafico_paridad(gen):
    fig = go.Figure()
    filas = {"pct_personas": "Personas portavoces", "pct_pantalla": "Tiempo en pantalla", "pct_habla": "Tiempo de voz"}
    for cat in gen.index:
        v = gen.loc[cat, list(filas)]
        nombre = NOMBRE_CATEGORIA.get(cat, cat)
        fig.add_bar(y=list(filas.values()), x=v, name=nombre, orientation="h",
                    marker=dict(color=COLOR_GENERO.get(cat, TINTA_3), line=dict(color="#fff", width=2)),
                    text=[f"{nombre} {x:.0f} %" for x in v], textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#fff"), hovertemplate=f"{nombre}: %{{x:.1f}} %<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, 100], title="% del total", ticksuffix=" %")
    return tema(fig, 260)


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
                    marker=dict(color=color.get(clave) or GRIS[clave], line=dict(color="#fff", width=2)),
                    customdata=d[["plano", "inicio_s", "dur_s"]],
                    hovertemplate="%{fullData.name}<br>plano %{customdata[0]} · min %{base:.1f}"
                                  "<br>%{customdata[2]:.0f} s<extra></extra>")
    if primera:
        fig.add_vline(x=primera / 60, line_dash="dash", line_color=TINTA_2, line_width=1,
                      annotation_text="turno de preguntas →", annotation_position="top right",
                      annotation_yshift=18, annotation_font=dict(color=TINTA_2))
    tema(fig, 260)
    fig.update_layout(barmode="overlay", bargap=0.15, barcornerradius=0, margin=dict(t=40),
                      legend=dict(orientation="h", y=-0.45, yanchor="top", x=0))
    fig.update_yaxes(visible=False)
    fig.update_xaxes(title="minuto de la emisión", ticksuffix="′")
    return fig


def grafico_flujo(cfg, pl, habla, nombres, color, medida):
    """Sankey al estilo de las infografías de referencia: del total a cada categoría y de ahí a cada persona."""
    cat_de = {g["persona"]: g.get("categoria") or "no_documentado" for g in cfg["grupos"] if g.get("persona")}
    if medida == "pantalla":
        persona_de = {g["id"]: g["persona"] for g in cfg["grupos"]}
        p = pl[pl["tipo"] != "excluir"]
        clave = [persona_de.get(g) or ("sala" if t == "plano_medio" else "plano_general") for g, t in zip(p["grupo"], p["tipo"])]
        valores = p.assign(clave=clave).groupby("clave")["dur_s"].sum() / 60
        origen = "Emisión"
    else:
        valores = habla["tiempo_habla_s"] / 60
        origen = "Voz transcrita"
    otros = {"sala": "Sala de prensa", "sin_atribuir": "Sin atribuir", "plano_general": "Plano general"}
    nodos, col_nodos, fuentes, destinos, vals, col_links = [origen], [TINTA], [], [], [], []

    def nodo(nombre, c):
        if nombre not in nodos:
            nodos.append(nombre)
            col_nodos.append(c)
        return nodos.index(nombre)

    def enlace(a, b, v, c):
        fuentes.append(a)
        destinos.append(b)
        vals.append(round(float(v), 2))
        col_links.append(f"rgba({int(c[1:3], 16)},{int(c[3:5], 16)},{int(c[5:7], 16)},0.35)")

    for cat in ["mujer", "hombre", "no_documentado"]:
        personas = [k for k in valores.index if cat_de.get(k) == cat]
        if not personas:
            continue
        nc = nodo(NOMBRE_CATEGORIA[cat], COLOR_GENERO[cat])
        enlace(0, nc, valores[personas].sum(), COLOR_GENERO[cat])
        for k in personas:
            enlace(nc, nodo(etiqueta(k, nombres), color.get(k, TINTA_3)), valores[k], color.get(k, TINTA_3))
    for k, txt in otros.items():
        if k in valores.index and valores[k] > 0:
            enlace(0, nodo(txt, GRIS[k]), valores[k], GRIS[k])
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=nodos, color=col_nodos, pad=18, thickness=14, line=dict(color="#fff", width=1),
                  hovertemplate="%{label}: %{value:.1f} min<extra></extra>"),
        link=dict(source=fuentes, target=destinos, value=vals, color=col_links,
                  hovertemplate="%{source.label} → %{target.label}: %{value:.1f} min<extra></extra>")))
    return tema(fig, 360)


def grafico_voz(habla, nombres, color):
    h = habla.sort_values("pct_habla")
    fig = go.Figure(go.Bar(y=[etiqueta(k, nombres) for k in h.index], x=h["pct_habla"], orientation="h",
                           marker=dict(color=[color.get(k) or GRIS.get(k, TINTA_3) for k in h.index]),
                           text=[f"{v:.1f} %" for v in h["pct_habla"]], textposition="outside",
                           textfont=dict(color=TINTA), customdata=h[["palabras", "tiempo_habla_s"]],
                           hovertemplate="%{y}: %{x:.1f} %<br>%{customdata[0]} palabras · "
                                         "%{customdata[1]:.0f} s<extra></extra>"))
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(title="% del tiempo de voz transcrito", range=[0, h["pct_habla"].max() * 1.25], ticksuffix=" %")
    return tema(fig, 360)


def turnos(pal, nombres):
    pal = pal[pal["hablante"] != "excluir"].copy()
    pal["turno"] = (pal["hablante"] != pal["hablante"].shift()).cumsum()
    t = pal.groupby("turno").agg(inicio_s=("inicio_s", "min"), fin_s=("fin_s", "max"),
                                 hablante=("hablante", "first"), texto=("palabra", " ".join))
    t["minuto"] = (t["inicio_s"] / 60).round(1)
    t["hablante"] = t["hablante"].map(lambda k: etiqueta(k, nombres))
    return t[["minuto", "hablante", "texto"]]


def tarjetas(kpis):
    caras = avatares(len(kpis))
    celdas = "".join(f'<div class="kpi"><div class="et">{et}</div><div class="val">{val}</div>'
                     f'<div class="sub">{sub}</div><img class="px" src="{b64(c)}" alt=""></div>'
                     for (et, val, sub), c in zip(kpis, caras))
    html(f'<div class="kpis">{celdas}</div>')


# ---------- Pestaña: resultados ----------
def pestana_resultados(cfg):
    out = Path(cfg["salida"])
    if not (out / "resumen.json").exists():
        titulo_seccion("Resumen del análisis", "Aún sin métricas", avatares(1)[0])
        st.info("Este análisis aún no tiene métricas. Complétalo en la pestaña **Análisis de vídeo**.")
        return
    res = leer(out / "resumen.json")
    gen = pd.read_csv(out / "metricas_genero.csv", index_col=0)
    habla = pd.read_csv(out / "metricas_habla.csv", index_col=0)
    per = pd.read_csv(out / "metricas_personas.csv")
    estr = pd.read_csv(out / "metricas_estructura.csv", index_col=0)
    fases = pd.read_csv(out / "metricas_fases.csv", index_col=0).reindex(columns=["exposicion", "preguntas"], fill_value=0)
    pl = pd.read_csv(out / "planos_clasificados.csv", keep_default_na=False)
    nombres = nombres_personas(cfg)
    color = colores_personas(nombres)

    titulo_seccion("Resumen del análisis", f'{cfg.get("titulo", cfg["nombre"])} · '
                   f'<a href="{cfg["fuente"]}" target="_blank">fuente</a>')
    m = gen.loc["mujer"] if "mujer" in gen.index else None
    pct = (lambda c: f"{m[c]:.0f} %") if m is not None else (lambda c: "–")
    tarjetas([
        ("Mujeres en pantalla", pct("pct_pantalla"),
         f"{m['personas']:.0f} de {gen['personas'].sum():.0f} portavoces" if m is not None else ""),
        ("Tiempo de voz · mujeres", pct("pct_habla"), "del tiempo de voz atribuido"),
        ("Paridad de voz · mujeres", f"{m['paridad_habla']:.2f}" if m is not None else "–", "1 = proporcional a cuántas son"),
        ("Abre / cierra", f"{etiqueta(res['abre'], nombres).split()[0]} / {etiqueta(res['cierra'], nombres).split()[0]}",
         "quién habla primero y último"),
        ("Emisión útil", f"{res['emision_util_s'] / 60:.0f} min", f"{res['pct_habla_sin_atribuir']} % de voz sin atribuir"),
    ])
    if len(gen.index) == 1:
        html(f'<div class="nota">En esta rueda de prensa solo comparecen {NOMBRE_CATEGORIA.get(gen.index[0], gen.index[0]).lower()}: '
             'la paridad es 1 por definición. Aquí lo interesante es el reparto entre personas.</div>')

    with st.container(border=True):
        titulo_seccion("Presencia en pantalla", "Quién ocupa cada plano, minuto a minuto")
        st.plotly_chart(grafico_linea_tiempo(pl, cfg, nombres, color, res["primera_pregunta_s"]), width="stretch")

    izq, der = st.columns([1.15, 1])
    with izq, st.container(border=True):
        titulo_seccion("Flujo del protagonismo", "Del total a cada género y a cada persona")
        medida = st.segmented_control("Medida", ["pantalla", "voz"], default="pantalla", key="medida_flujo",
                                      format_func={"pantalla": "Tiempo en pantalla", "voz": "Tiempo de voz"}.get,
                                      label_visibility="collapsed") or "pantalla"
        st.plotly_chart(grafico_flujo(cfg, pl, habla, nombres, color, medida), width="stretch")
    with der, st.container(border=True):
        titulo_seccion("Reparto de la voz", "% del tiempo de voz transcrito")
        st.plotly_chart(grafico_voz(habla, nombres, color), width="stretch")

    with st.container(border=True):
        titulo_seccion("¿Es proporcional el protagonismo?", "Paridad = % obtenido / % de personas")
        st.plotly_chart(grafico_paridad(gen), width="stretch")

    with st.container(border=True):
        titulo_seccion("Por persona", "Tiempos, intervenciones y fase de la rueda de prensa")
        tabla = per.merge(estr, left_on="persona", right_index=True).merge(fases, left_on="persona", right_index=True)
        tabla["persona"] = tabla["persona"].map(nombres)
        st.dataframe(tabla[["persona", "categoria", "tiempo_pantalla_s", "tiempo_habla_s", "palabras",
                            "intervenciones", "duracion_media_s", "exposicion", "preguntas"]].round(1),
                     hide_index=True, width="stretch",
                     column_config={"tiempo_pantalla_s": "pantalla (s)", "tiempo_habla_s": "voz (s)",
                                    "duracion_media_s": "media interv. (s)", "exposicion": "exposición (s)",
                                    "preguntas": "preguntas (s)"})
        with st.expander("Tabla por género"):
            st.dataframe(gen.round(2), width="stretch")

    pal_ruta = out / "palabras_atribuidas.csv"
    if pal_ruta.exists():
        with st.container(border=True):
            titulo_seccion("Transcripción por turnos", "Cada palabra, atribuida a quien está en pantalla")
            t = turnos(pd.read_csv(pal_ruta, keep_default_na=False), nombres)
            f1, f2 = st.columns([1, 2])
            quien = f1.multiselect("Hablante", sorted(t["hablante"].unique()))
            buscar = f2.text_input("Buscar en el texto")
            if quien:
                t = t[t["hablante"].isin(quien)]
            if buscar:
                t = t[t["texto"].str.contains(buscar, case=False, regex=False)]
            st.dataframe(t, hide_index=True, width="stretch", height=320,
                         column_config={"texto": st.column_config.TextColumn(width="large")})

    with st.container(border=True):
        titulo_seccion("Descargas", "Datos abiertos de este análisis")
        d = st.columns(4)
        for col, f in zip(d, ["informe.md", "metricas_personas.csv", "metricas_genero.csv", "palabras_atribuidas.csv"]):
            if (out / f).exists():
                col.download_button(f, (out / f).read_bytes(), file_name=f"{cfg['nombre']}_{f}", width="stretch")


# ---------- Pestaña: comparar ----------
def pestana_comparar():
    titulo_seccion("Comparativas", "Todas las ruedas de prensa analizadas que puedes ver", avatares(1)[0])
    filas = []
    for nombre, ruta in visibles().items():
        cfg = pipeline.cargar_config(ruta)
        f = Path(cfg["salida"]) / "metricas_genero.csv"
        if f.exists():
            filas.append(pd.read_csv(f).assign(video=cfg.get("titulo", nombre).replace("Consejo de Ministros ", "")))
    if len(filas) < 2:
        st.info("Hace falta analizar al menos dos ruedas de prensa para comparar. "
                f"Ahora hay {len(filas)} con métricas.")
        if not filas:
            return
    df = pd.concat(filas)
    df["Categoría"] = df["categoria"].map(lambda c: NOMBRE_CATEGORIA.get(c, c))
    with st.container(border=True):
        titulo_seccion("Índice de paridad por rueda de prensa", "1 = protagonismo proporcional al número de personas")
        medida = st.segmented_control("Medida", ["habla", "pantalla"], default="habla", key="medida_comp",
                                      format_func={"habla": "Voz", "pantalla": "Pantalla"}.get,
                                      label_visibility="collapsed") or "habla"
        fig = go.Figure()
        for cat in df["categoria"].unique():
            d = df[df["categoria"] == cat]
            nombre = NOMBRE_CATEGORIA.get(cat, cat)
            fig.add_bar(x=d["video"], y=d[f"paridad_{medida}"], name=nombre, marker_color=COLOR_GENERO.get(cat, TINTA_3),
                        marker_line=dict(color="#fff", width=2),
                        hovertemplate=f"{nombre} · %{{x}}<br>paridad %{{y:.2f}}<extra></extra>")
        fig.add_hline(y=1, line_dash="dash", line_color=TINTA_2, annotation_text="proporcional")
        fig.update_layout(barmode="group", bargap=0.55, bargroupgap=0.08)
        fig.update_yaxes(title=f"índice de paridad ({'voz' if medida == 'habla' else 'pantalla'})")
        st.plotly_chart(tema(fig, 360), width="stretch")
    with st.container(border=True):
        titulo_seccion("Tabla comparativa")
        st.dataframe(df[["video", "Categoría", "personas", "pct_personas", "pct_pantalla", "paridad_pantalla",
                         "pct_habla", "paridad_habla"]].round(2), hide_index=True, width="stretch")


# ---------- Pestaña: sobre el proyecto ----------
def pestana_proyecto():
    caras = avatares(4)
    titulo_seccion("¿Cómo funciona?", "IA abierta, datos públicos y perspectiva de género")
    pasos = [("Analizamos el contenido", "Cortes de plano (PySceneDetect), personas (YOLO11 + ByteTrack) y rótulos (EasyOCR)."),
             ("Extraemos información", "Transcripción palabra a palabra con Whisper y atribución de cada palabra a quien sale en pantalla."),
             ("Identificamos con fuentes públicas", "Quién habla y su cargo salen de La Moncloa. El género se documenta, nunca se infiere de la cara."),
             ("Medimos el protagonismo", "Tiempo en pantalla y de voz, intervenciones, quién abre y cierra, e índice de paridad.")]
    html('<div class="pasos">' + "".join(
        f'<div class="paso"><img class="px" src="{b64(c)}" alt=""><span class="n">{i}</span><b>{t}</b><p>{d}</p></div>'
        for i, ((t, d), c) in enumerate(zip(pasos, caras), 1)) + "</div>")
    st.write("")
    izq, der = st.columns(2)
    with izq, st.container(border=True):
        titulo_seccion("Métricas", "Qué significa cada indicador")
        st.markdown("- **Tiempo en pantalla:** segundos en primer plano de cada persona.\n"
                    "- **Tiempo de voz:** duración de las palabras atribuidas a cada persona.\n"
                    "- **Intervenciones:** número de primeros planos y su duración media.\n"
                    "- **Abre / cierra:** quién habla primero y último.\n"
                    "- **Índice de paridad:** % obtenido / % de personas. 1 = proporcional; > 1 = sobrerrepresentación.")
    with der, st.container(border=True):
        titulo_seccion("Ética y código abierto", "Decisiones de diseño")
        st.markdown("- La categoría de género sale del **cargo oficial** publicado (Ministra / Ministro), no de la imagen.\n"
                    "- Solo se analizan **comparecencias públicas** de cargos públicos.\n"
                    "- Todo el código, los modelos y las métricas son **abiertos y reproducibles** (AGPL-3.0).\n"
                    "- Cada resultado guarda su **fuente** y la huella del vídeo y del código.")


def pie():
    logos = [("ministerio_comunidad.jpg", "Comunidad de IA de Código Abierto · Ministerio para la Transformación Digital y de la Función Pública"),
             ("prtr.jpg", "Plan de Recuperación, Transformación y Resiliencia"),
             ("nextgeneu.jpg", "Financiado por la Unión Europea · NextGenerationEU"),
             ("espana_digital.jpg", "España Digital 2026")]
    html('<div class="pie"><div class="fila">' + "".join(
        f'<img src="{b64(ASSETS / "logos" / f)}" alt="{alt}" title="{alt}">' for f, alt in logos) +
         '</div><small>Reto «Mujeres por la IA Abierta» · SEDIA · Colaboran UPC-IDEAI, COEINF (donesCOEINF) y OVHcloud · '
         'Equipo 5: Firdaous, Nouhaila y Paula</small></div>')


# ---------- Pestaña: nuevo análisis / continuar ----------
def formulario_moncloa():
    """Ruedas de prensa de La Moncloa: todo automático (vídeo, quién habla, categoría por cargo oficial)."""
    with st.form("moncloa", border=False):
        titulo_seccion("Ruedas de prensa de La Moncloa", "Automático, sin revisión manual")
        st.caption("El sistema descarga el vídeo, identifica a cada persona con la página de La Moncloa y su aspecto en "
                   "el propio vídeo, toma la categoría del cargo oficial (Ministra/Ministro) y calcula las métricas.")
        urls = st.text_area("Enlaces de páginas de rueda de prensa (uno por línea)",
                            placeholder="https://www.lamoncloa.gob.es/consejodeministros/resumenes/Paginas/2026/201026-rueda-prensa-ministros.aspx")
        recientes = st.checkbox("Añadir todas las del índice de La Moncloa (las más recientes)")
        if not st.form_submit_button("Analizar"):
            return
    lista_urls = [u.strip() for u in urls.splitlines() if u.strip()]
    with st.spinner("Leyendo La Moncloa..."):
        if recientes:
            lista_urls += moncloa.paginas_recientes()
        for url in dict.fromkeys(lista_urls):
            try:
                st.success(moncloa.encolar(url))
            except Exception as e:
                st.error(f"{url}: {e}")


def formulario_nuevo():
    with st.form("nuevo", border=False):
        titulo_seccion("Analizar un vídeo propio", "Sube un vídeo y documenta quién comparece")
        titulo = st.text_input("Título", placeholder="Consejo de Ministros 20/10/2026")
        subido = st.file_uploader("Vídeo", type=["mp4", "mov", "mkv", "avi", "webm"])
        with st.expander("…o ruta de un vídeo que ya esté en el servidor"):
            ruta_video = st.text_input("Ruta (absoluta o relativa a la carpeta del proyecto)", placeholder="NOA/consejo_201026.mp4")
        fuente = st.text_input("Fuente pública que documenta quién comparece", placeholder="https://www.lamoncloa.gob.es/...")
        whisper = st.selectbox("Modelo de transcripción", ["large-v3", "medium", "small"], index=0 if HAY_GPU else 1,
                               help="large-v3 es el más preciso; en CPU, medium (bueno) o small (más rápido)")
        if not st.form_submit_button("Crear"):
            return
    if not slug(titulo) or not (subido or ruta_video) or not fuente:
        st.error("Rellena título, vídeo y fuente.")
        return
    codigo = secrets.token_hex(4)
    nombre = f"{slug(titulo)[:40]}_{codigo[:4]}"           # el sufijo evita choques entre usuarias
    if subido:
        VIDEOS.mkdir(exist_ok=True)
        destino = VIDEOS / f"{nombre}{Path(subido.name).suffix.lower()}"
        with open(destino, "wb") as f:
            shutil.copyfileobj(subido, f, 16 * 1024 * 1024)
        video = str(destino.relative_to(RAIZ))
    else:
        video = ruta_video
        if not (RAIZ / video).exists():
            st.warning("No encuentro el vídeo en esta máquina. Se crea el análisis igualmente (la visión fallará hasta que exista).")
    base = leer(VISION / "config.json") if (VISION / "config.json").exists() else {}
    modelo = VISION / "modelos" / "yolo11m.pt"
    # Sin GPU (modo CPU): menos fotogramas y rótulos por segundo para que un vídeo tarde en torno a una hora
    calidad = ({"muestras_s": 10, "imgsz": 960, "ocr_cada_s": 0.5} if HAY_GPU else
               {"muestras_s": 2, "imgsz": 640, "ocr_cada_s": 2.0})
    guardar(VISION / f"config_{nombre}.json", {
        **{"inicio_s": 0.0, "fin_s": None, "conf_ocr": 0.6},
        **{k: v for k, v in base.items() if k not in ("video", "salida", "modelo", *calidad)},
        **calidad, "exigir_gpu": HAY_GPU,
        # rutas relativas a la raíz del repositorio, para que el análisis se pueda repetir en otra máquina
        "video": video, "salida": f"PAULA/consejo_integrado/resultados_{nombre}",
        "modelo": str(modelo.relative_to(RAIZ)) if modelo.exists() else "yolo11m.pt"})
    plantilla = leer(FIR / "config_131026.json")
    guardar(FIR / f"config_{nombre}.json", {
        "nombre": nombre, "titulo": titulo, "codigo": codigo, "video": video,
        "resultados_vision": f"PAULA/consejo_integrado/resultados_{nombre}",
        "salida": f"FIRDAOUS/salidas/{nombre}", "fuente": fuente, "excluir_planos": [],
        "umbrales": plantilla["umbrales"], "modelo_whisper": whisper, "grupos": []})
    recordar_codigo(codigo)
    st.session_state["analisis"] = nombre
    st.session_state["recien_creado"] = codigo
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
            st.info("Modo CPU (sin GPU): analiza 2 fotogramas por segundo. Un vídeo de 20 min tarda del orden de una hora.")
        if st.button("Lanzar visión" if not hecho_v else "Relanzar (reanuda planos pendientes)", key="v"):
            cola.encolar("vision", R, [sys.executable, RAIZ / "analizar_video.py", vcfg, ruta])
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
                st.markdown("**a) Personas.** Una fila por persona que comparece. Si hay rótulos con su nombre, pon en "
                            "*texto* lo que lee el OCR (ver candidatos) y sus planos se asignan solos; los textos se comprueban "
                            "en orden y uno vacío recoge lo que quede. La categoría se toma de la fuente pública, "
                            "**nunca de la imagen**.")
                st.markdown("Textos candidatos (rótulos de primeros planos)")
                st.dataframe(sugerir_rotulos(pl), hide_index=True, width="stretch")
                grupos = pd.DataFrame(cfg_crudo["grupos"], columns=["id", "texto", "nombre", "persona", "categoria"])
                editado = st.data_editor(grupos, num_rows="dynamic", width="stretch", key="grupos",
                                         column_config={"categoria": st.column_config.SelectboxColumn(options=CATEGORIAS),
                                                        "persona": st.column_config.TextColumn(help="Se rellena solo a partir del nombre")})
                st.markdown("**b) Plano a plano.** Comprueba con las miniaturas quién sale en cada primer plano y "
                            "corrige la columna *grupo* si hace falta (imprescindible si el vídeo no tiene rótulos).")
                pp = pl.loc[pl["tipo"] == "primer_plano", ["plano", "inicio_s", "dur_s", "grupo", "rotulos"]].copy()
                pp["minuto"] = (pp["inicio_s"] / 60).round(1)
                ids = [g["id"] for g in cfg_crudo["grupos"]]
                asignado = st.data_editor(pp[["plano", "minuto", "dur_s", "grupo", "rotulos"]].round(1), hide_index=True,
                                          width="stretch", height=250, key="asignacion",
                                          disabled=["plano", "minuto", "dur_s", "rotulos"],
                                          column_config={"grupo": st.column_config.SelectboxColumn(options=["", "?", *ids])})
                miniaturas = {int(p.stem[5:]): p for p in (out / "revision").glob("primer_plano*/plano*.jpg")} \
                    if (out / "revision").exists() else {}
                if miniaturas:
                    cols = st.columns(6)
                    for i, (_, f) in enumerate(pp.iterrows()):
                        if int(f["plano"]) in miniaturas:
                            cols[i % 6].image(str(miniaturas[int(f["plano"])]), width="stretch",
                                              caption=f"plano {int(f['plano'])} · grupo {f['grupo'] or '–'}")
                else:
                    st.caption("Sin miniaturas en esta máquina (los recortes están donde se ejecutó la visión).")
                excluir = st.multiselect("Planos a excluir (cabeceras, rótulos, vídeos insertados)",
                                         pl["plano"].tolist(), default=cfg_crudo["excluir_planos"])
                if st.button("Guardar y reclasificar", type="primary"):
                    filas = editado.fillna("").astype(str).to_dict("records")
                    for i, g in enumerate(filas):
                        g["id"] = g["id"] or chr(65 + i)
                        g["persona"] = g["persona"] or slug(g["nombre"])
                    manual = dict(cfg_crudo.get("asignacion_manual", {}))
                    for antes, despues in zip(pp.itertuples(), asignado.itertuples()):
                        if (despues.grupo or "") != (antes.grupo or ""):
                            manual[str(int(antes.plano))] = despues.grupo or ""
                    cfg_crudo.update(grupos=[g for g in filas if g["persona"] or g["texto"]], excluir_planos=excluir,
                                     asignacion_manual=manual)
                    guardar(ruta, cfg_crudo)
                    ejecutar_fase(ruta, "revisar")

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
            cola.encolar("metricas", out, [sys.executable, FIR / "pipeline.py", ruta, "metricas"])
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
html(CSS)
with st.sidebar:
    st.image(str(ASSETS / "logos" / "girls_in_the_loop.png"), width="stretch")
    st.caption("Protagonismo por género en ruedas de prensa · Equipo 5")
    lista = visibles()
    if not lista:
        st.stop()
    nombres_cfg = list(lista)
    elegido = st.selectbox("Rueda de prensa", nombres_cfg,
                           format_func=lambda n: leer(lista[n]).get("titulo", n),
                           index=nombres_cfg.index(st.session_state.get("analisis", nombres_cfg[0]))
                           if st.session_state.get("analisis") in nombres_cfg else 0)
    st.session_state["analisis"] = elegido
    with st.form("codigo", border=False):
        nuevo = st.text_input("¿Tienes un código de análisis?", placeholder="p. ej. 3fa9c2d1")
        if st.form_submit_button("Abrir") and nuevo.strip():
            recordar_codigo(nuevo.strip())
            st.rerun()
    st.divider()
    st.markdown("**Entorno de esta máquina**")
    for ok, txt in [(shutil.which("ffmpeg") is not None, "FFmpeg"), (HAY_GPU, "GPU NVIDIA"), (HAY_WHISPER, "faster-whisper")]:
        st.markdown(f"{'✅' if ok else '⚠️'} {txt}")
    if not HAY_GPU:
        st.caption("Sin GPU los vídeos nuevos se analizan en modo CPU: funciona, pero más despacio.")
    st.image(str(avatares(1, grandes=True)[0]), width="stretch")

if cola.pendientes() and not cola.activo():      # si el servidor se reinició, retomar la cola
    cola.arrancar()

cfg_sel = pipeline.cargar_config(lista[elegido])
privado = '<span class="chip priv">🔒 privado · código ' + cfg_sel["codigo"] + "</span>" if cfg_sel.get("codigo") else ""
html(f'<div class="hero"><div><img class="logo" src="{b64(ASSETS / "logos" / "girls_in_the_loop.png")}" alt="Girls in the Loop">'
     '<p>Analizamos la presencia y el protagonismo de las mujeres en el contenido audiovisual con IA abierta, '
     'datos públicos y perspectiva de género.</p>'
     f'<span class="chip">{cfg_sel.get("titulo", elegido)}</span>{privado}</div>'
     '<div class="tira">' + "".join(f'<img class="px" src="{b64(a)}" alt="">' for a in avatares(5)) + "</div></div>")
if cfg_sel.get("codigo"):
    st.caption("Guarda el enlace de esta página (lleva tu código) para volver o compartirlo; sin él no se puede ver.")
if st.session_state.pop("recien_creado", None):
    st.success("Análisis creado. Sigue los pasos de la pestaña **Análisis de vídeo**.")
t1, t2, t3, t4 = st.tabs(["Resumen", "Análisis de vídeo", "Comparativas", "Sobre el proyecto"])
with t1:
    pestana_resultados(cfg_sel)
with t2:
    titulo_seccion("Análisis de vídeo", "Lanza análisis nuevos o sigue el estado de los que están en marcha", avatares(1)[0])
    with st.container(border=True):
        formulario_moncloa()
    with st.container(border=True):
        formulario_nuevo()
    with st.container(border=True):
        titulo_seccion(f"Pasos de «{cfg_sel.get('titulo', elegido)}»", "Visión → quién es quién → métricas → informe")
        pestana_proceso(elegido, lista[elegido])
with t3:
    pestana_comparar()
with t4:
    pestana_proyecto()
pie()
