"""Girls in the Loop: protagonismo por género en ruedas de prensa.
Uso: python pipeline.py CONFIG.json revisar|metricas|informe
"""
import json, os, shutil, subprocess, sys, time, wave
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # carpeta equipo5


def cargar_config(ruta):
    """Lee el config; las rutas relativas se resuelven desde la raíz del repo (VM o portátil)."""
    cfg = json.load(open(ruta, encoding="utf-8"))
    for k in ("video", "resultados_vision", "salida"):
        cfg[k] = os.path.join(RAIZ, cfg[k])
    return cfg


# ---------- Planos: tipo y grupo ----------
def construir_planos(cfg):
    R = cfg["resultados_vision"]
    pl = pd.read_csv(f"{R}/planos.csv")
    tr = pd.read_csv(f"{R}/resumen_tracks.csv")
    ev = pd.read_csv(f"{R}/eventos_texto.csv")
    ev["dur"] = ev["fin_s"] - ev["inicio_s"]
    tr["peso"] = tr["tiempo_detectado_s"] * tr["area_media_pct"]

    filas = []
    for _, p in pl.iterrows():
        t = tr[tr["plano"] == p["plano"]]
        pr = t.loc[t["peso"].idxmax()] if len(t) else None
        textos = " || ".join(ev[(ev["plano"] == p["plano"]) & (ev["dur"] >= 1)]["texto"].unique())
        filas.append({
            "plano": int(p["plano"]), "inicio_s": p["inicio_s"], "fin_s": p["fin_s"],
            "dur_s": p["fin_s"] - p["inicio_s"], "n_tracks": len(t),
            "track_principal": pr["track_id"] if pr is not None else "",
            "area_pct": pr["area_media_pct"] if pr is not None else 0.0,
            "rotulos": textos,
        })
    return pd.DataFrame(filas)


def clasificar(df, cfg):
    u = cfg["umbrales"]

    def tipo(f):
        if f["n_tracks"] == 0 or f["plano"] in cfg["excluir_planos"]:
            return "excluir"
        if f["n_tracks"] <= u["max_personas_primer_plano"] and f["area_pct"] >= u["min_area_primer_plano"]:
            return "primer_plano"
        if f["area_pct"] >= u["min_area_plano_medio"]:
            return "plano_medio"
        return "plano_general"

    def grupo(f):
        if f["tipo"] != "primer_plano":
            return ""
        for g in cfg["grupos"]:
            if g["texto"] == "" or g["texto"] in f["rotulos"]:
                return g["id"]
        return "?"

    df["tipo"] = df.apply(tipo, axis=1)
    df["grupo"] = df.apply(grupo, axis=1)
    return df


# ---------- Fase 1: revisar ----------
def fase_revisar(cfg):
    out = cfg["salida"]
    os.makedirs(out, exist_ok=True)
    pl = clasificar(construir_planos(cfg), cfg)
    pl.to_csv(f"{out}/planos_clasificados.csv", index=False)

    rec = pd.read_csv(f"{cfg['resultados_vision']}/recortes.csv")
    shutil.rmtree(f"{out}/revision", ignore_errors=True)
    for _, f in pl[pl["tipo"] != "excluir"].iterrows():
        r = rec[rec["track"] == f["track_principal"]]
        if r.empty:
            continue
        fila = r.iloc[len(r) // 2]
        origen = os.path.join(cfg["resultados_vision"], fila["path"])
        if not os.path.exists(origen):
            continue
        carpeta = f"{out}/revision/{f['tipo']}" + (f"_{f['grupo']}" if f["grupo"] else "")
        os.makedirs(carpeta, exist_ok=True)
        shutil.copy(origen, f"{carpeta}/plano{int(f['plano']):02d}.jpg")

    print(pl.groupby(["tipo", "grupo"]).agg(planos=("plano", "count"), dur_s=("dur_s", "sum")).round(1).to_string())
    print(f"\nRevisa {out}/revision y completa persona y categoria de cada grupo en el config.")


# ---------- Transcripción (se guarda y se reutiliza) ----------
def transcribir(cfg):
    out = cfg["salida"]
    ruta = f"{out}/transcripcion_palabras.csv"
    if os.path.exists(ruta):
        print("Transcripción ya existente, se reutiliza.")
        return pd.read_csv(ruta)

    wav = f"{out}/audio.wav"
    if not os.path.exists(wav):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", cfg["video"],
                        "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    with wave.open(wav) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

    import ctranslate2
    from faster_whisper import WhisperModel
    t0 = time.time()
    gpu = ctranslate2.get_cuda_device_count() > 0
    print("Transcribiendo en", "GPU" if gpu else "CPU (lento)", flush=True)
    modelo = WhisperModel(cfg["modelo_whisper"], device="cuda" if gpu else "cpu",
                          compute_type="float16" if gpu else "int8")
    segmentos, _ = modelo.transcribe(audio, language="es", vad_filter=True, word_timestamps=True)
    palabras = [{"inicio_s": round(p.start, 2), "fin_s": round(p.end, 2), "palabra": p.word.strip()}
                for s in segmentos for p in s.words]
    df = pd.DataFrame(palabras)
    df.to_csv(ruta, index=False)
    print(f"Transcritas {len(df)} palabras en {time.time() - t0:.0f} s")
    return df


# ---------- Fase 2: métricas ----------
def fase_metricas(cfg):
    out, R = cfg["salida"], cfg["resultados_vision"]
    grupos = {g["id"]: g for g in cfg["grupos"]}
    falta = [g["id"] for g in cfg["grupos"] if not g.get("persona") or not g.get("categoria")]
    if falta:
        sys.exit(f"Faltan persona/categoria en los grupos {falta}. Ejecuta 'revisar' y completa el config.")

    pl = pd.read_csv(f"{out}/planos_clasificados.csv", keep_default_na=False)
    pl["persona"] = pl["grupo"].map(lambda g: grupos[g]["persona"] if g in grupos else "")
    pl["categoria"] = pl["grupo"].map(lambda g: grupos[g]["categoria"] if g in grupos else "")
    util = pl.loc[pl["tipo"] != "excluir", "dur_s"].sum()

    # Identidades documentadas
    cp = pl[pl["persona"] != ""].sort_values("inicio_s").copy()
    ids = cp[["track_principal", "persona", "categoria"]].rename(columns={"track_principal": "track_id"})
    ids["fuente"] = cfg["fuente"]
    ids.to_csv(f"{out}/identidades_documentadas.csv", index=False)

    # Presencia y prominencia
    tr = pd.read_csv(f"{R}/resumen_tracks.csv").merge(ids, on="track_id")
    personas = (tr.groupby(["persona", "categoria"])
                  .agg(tiempo_pantalla_s=("tiempo_detectado_s", "sum"), planos=("plano", "nunique"),
                       area_media_pct=("area_media_pct", "mean")).reset_index())
    personas["pct_emision_util"] = 100 * personas["tiempo_pantalla_s"] / util

    # Estructura y fases
    primera_pregunta = pl.loc[pl["tipo"] == "plano_medio", "inicio_s"].min()
    if pd.isna(primera_pregunta):
        primera_pregunta = float("inf")
    cp["fase"] = np.where(cp["inicio_s"] < primera_pregunta, "exposicion", "preguntas")
    estructura = cp.groupby("persona").agg(intervenciones=("plano", "count"), duracion_media_s=("dur_s", "mean"),
                                           primera_aparicion_s=("inicio_s", "min"))
    fases = cp.pivot_table(index="persona", columns="fase", values="dur_s", aggfunc="sum", fill_value=0)

    # Habla: cada palabra se asigna al plano en el que se dice
    pal = transcribir(cfg).sort_values("inicio_s", kind="stable")   # estable: respeta el orden entre empates
    pal["dur"] = pal["fin_s"] - pal["inicio_s"]
    pal = pd.merge_asof(pal, pl[["inicio_s", "tipo", "persona"]].rename(columns={"inicio_s": "plano_ini"}),
                        left_on="inicio_s", right_on="plano_ini", direction="backward")
    otros = {"plano_medio": "sala", "plano_general": "sin_atribuir", "excluir": "excluir"}
    pal["hablante"] = [p if p else otros.get(t, "sin_atribuir") for p, t in zip(pal["persona"], pal["tipo"])]
    pal.to_csv(f"{out}/palabras_atribuidas.csv", index=False)
    habla = (pal[pal["hablante"] != "excluir"].groupby("hablante")
               .agg(palabras=("palabra", "count"), tiempo_habla_s=("dur", "sum")))
    habla["pct_habla"] = 100 * habla["tiempo_habla_s"] / habla["tiempo_habla_s"].sum()

    personas = personas.merge(habla[["palabras", "tiempo_habla_s"]], left_on="persona", right_index=True, how="left")
    personas["pct_plano_con_voz"] = 100 * personas["tiempo_habla_s"] / personas["tiempo_pantalla_s"]

    # Género: porcentajes e índices de paridad
    g = personas.groupby("categoria").agg(personas=("persona", "count"), tiempo_pantalla_s=("tiempo_pantalla_s", "sum"),
                                          tiempo_habla_s=("tiempo_habla_s", "sum"))
    g["pct_personas"] = 100 * g["personas"] / g["personas"].sum()
    for m in ["pantalla", "habla"]:
        g[f"pct_{m}"] = 100 * g[f"tiempo_{m}_s"] / g[f"tiempo_{m}_s"].sum()
        g[f"paridad_{m}"] = g[f"pct_{m}"] / g["pct_personas"]

    # Guardar y mostrar
    for nombre, df in {"personas": personas, "genero": g, "estructura": estructura,
                       "fases": fases, "habla": habla}.items():
        df.round(2).to_csv(f"{out}/metricas_{nombre}.csv", index=(nombre != "personas"))
    resumen = {"video": cfg["nombre"], "emision_util_s": round(util, 1),
               "abre": cp.iloc[0]["persona"], "cierra": cp.iloc[-1]["persona"],
               "primera_pregunta_s": None if primera_pregunta == float("inf") else round(primera_pregunta, 1),
               "pct_habla_sin_atribuir": round(habla["pct_habla"].get("sin_atribuir", 0), 1)}
    json.dump(resumen, open(f"{out}/resumen.json", "w"), ensure_ascii=False, indent=1)

    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print("\n", personas.round(1).to_string(index=False))
    print("\n", g.round(2).to_string())
    print("\n", fases.round(1).to_string())


# ---------- Fase 3: informe (gráficos + resumen, sin GPU) ----------
COLOR_PERSONA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",     # paleta categórica validada, orden fijo;
                 "#e87ba4", "#008300", "#6250d6", "#e34948"]     # a partir de la 9.ª persona: gris
COLOR_GENERO = {"mujer": "#eb6834", "hombre": "#2a78d6"}
GRIS = {"sala": "#8a8984", "sin_atribuir": "#c9c8c2", "plano_general": "#e4e3de", "excluir": "#ffffff"}


def colores_personas(personas):
    return {p: COLOR_PERSONA[i] if i < len(COLOR_PERSONA) else "#52514e" for i, p in enumerate(personas)}


def fase_informe(cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = cfg["salida"]
    os.makedirs(f"{out}/graficos", exist_ok=True)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#52514e", "text.color": "#0b0b0b", "axes.labelcolor": "#52514e"})

    nombres = {g["persona"]: g.get("nombre", g["persona"].replace("_", " ").title()) for g in cfg["grupos"]}
    color = colores_personas(nombres)
    res = json.load(open(f"{out}/resumen.json", encoding="utf-8"))
    pl = pd.read_csv(f"{out}/planos_clasificados.csv", keep_default_na=False)
    gen = pd.read_csv(f"{out}/metricas_genero.csv", index_col=0)
    habla = pd.read_csv(f"{out}/metricas_habla.csv", index_col=0)
    per = pd.read_csv(f"{out}/metricas_personas.csv")
    fases = pd.read_csv(f"{out}/metricas_fases.csv", index_col=0)
    estr = pd.read_csv(f"{out}/metricas_estructura.csv", index_col=0)

    # 1. Paridad: presencia esperada (% personas) frente a pantalla y voz
    fig, ax = plt.subplots(figsize=(8, 3.2))
    metricas = [("pct_personas", "Personas portavoces"), ("pct_pantalla", "Tiempo en pantalla"), ("pct_habla", "Tiempo de voz")]
    izq = np.zeros(len(metricas))
    for cat in gen.index:
        v = gen.loc[cat, [m for m, _ in metricas]].to_numpy(float)
        ax.barh(range(len(metricas)), v, left=izq, color=COLOR_GENERO.get(cat, "#8a8984"),
                edgecolor="white", linewidth=2, label=cat)
        for i, (x, w) in enumerate(zip(izq, v)):
            ax.text(x + w / 2, i, f"{cat} {w:.0f} %", ha="center", va="center", color="white", fontsize=10)
        izq += v
    ax.set_yticks(range(len(metricas)), [n for _, n in metricas])
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("% del total")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(gen), frameon=False)
    fig.tight_layout(); fig.savefig(f"{out}/graficos/1_paridad.png", dpi=150); plt.close(fig)

    # 2. Línea de tiempo: quién ocupa la pantalla en cada plano
    fig, ax = plt.subplots(figsize=(10, 2.6))
    util_pl = pl[pl["tipo"] != "excluir"]
    ax.set_xlim(util_pl["inicio_s"].min() / 60, (util_pl["inicio_s"] + util_pl["dur_s"]).max() / 60)
    ax.set_ylim(-0.35, 0.6)
    for _, p in pl.iterrows():
        persona = next((g["persona"] for g in cfg["grupos"] if g["id"] == p["grupo"]), "")
        c = color.get(persona) or GRIS["sala" if p["tipo"] == "plano_medio" else p["tipo"]]
        ax.barh(0, p["dur_s"] / 60, left=p["inicio_s"] / 60, color=c, height=0.6)
    if res["primera_pregunta_s"]:
        x = res["primera_pregunta_s"] / 60
        ax.axvline(x, color="#0b0b0b", linewidth=1, linestyle="--")
        ax.text(x, 0.36, " turno de preguntas →", fontsize=9, va="bottom")
    ax.set_yticks([]); ax.set_xlabel("minuto de la emisión"); ax.spines["left"].set_visible(False)
    leyenda = [plt.Rectangle((0, 0), 1, 1, color=color[p]) for p in nombres] + \
              [plt.Rectangle((0, 0), 1, 1, color=GRIS[k]) for k in ("sala", "plano_general")]
    ax.legend(leyenda, list(nombres.values()) + ["sala de prensa", "plano general"],
              loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=5, frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(f"{out}/graficos/2_linea_tiempo.png", dpi=150); plt.close(fig)

    # 3. Reparto del tiempo de voz por hablante
    h = habla.sort_values("pct_habla")
    fig, ax = plt.subplots(figsize=(8, 3.2))
    etiquetas = [nombres.get(k, {"sala": "Sala de prensa", "sin_atribuir": "Sin atribuir"}.get(k, k)) for k in h.index]
    ax.barh(etiquetas, h["pct_habla"], color=[color.get(k, GRIS.get(k, "#8a8984")) for k in h.index], height=0.6)
    for i, v in enumerate(h["pct_habla"]):
        ax.text(v + 0.5, i, f"{v:.1f} %", va="center", fontsize=10)
    ax.set_xlabel("% del tiempo de voz transcrito")
    fig.tight_layout(); fig.savefig(f"{out}/graficos/3_voz.png", dpi=150); plt.close(fig)

    # Informe en Markdown
    tabla = per.merge(estr, left_on="persona", right_index=True)[
        ["persona", "categoria", "tiempo_pantalla_s", "pct_emision_util", "tiempo_habla_s", "palabras",
         "intervenciones", "duracion_media_s"]]
    tabla["persona"] = tabla["persona"].map(nombres)
    md = [f"# Informe: {cfg['nombre']}", "", f"Fuente: {cfg['fuente']}", "",
          f"- Emisión útil analizada: {res['emision_util_s'] / 60:.1f} min",
          f"- Abre: {nombres.get(res['abre'], res['abre'])} · Cierra: {nombres.get(res['cierra'], res['cierra'])}",
          f"- Turno de preguntas desde el minuto {res['primera_pregunta_s'] / 60:.1f}" if res["primera_pregunta_s"] else "- Sin turno de preguntas detectado",
          f"- Voz sin atribuir: {res['pct_habla_sin_atribuir']} %", "",
          "## Paridad por género", "", "Índice de paridad = % obtenido / % de personas (1 = proporcional).", "",
          gen.round(2).to_markdown(), "", "![](graficos/1_paridad.png)", "",
          "## Por persona", "", tabla.round(1).to_markdown(index=False), "",
          "## Exposición frente a preguntas (s en primer plano)", "",
          fases.rename(index=nombres).round(1).to_markdown(), "", "![](graficos/2_linea_tiempo.png)", "",
          "## Reparto de la voz", "", "![](graficos/3_voz.png)", ""]
    open(f"{out}/informe.md", "w", encoding="utf-8").write("\n".join(md))
    print(f"Informe y gráficos en {out}/informe.md y {out}/graficos/")


if __name__ == "__main__":
    fases_cli = {"revisar": fase_revisar, "metricas": fase_metricas, "informe": fase_informe}
    if len(sys.argv) != 3 or sys.argv[2] not in fases_cli:
        sys.exit("Uso: python pipeline.py CONFIG.json revisar|metricas|informe")
    fases_cli[sys.argv[2]](cargar_config(sys.argv[1]))