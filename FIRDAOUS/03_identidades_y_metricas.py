import pandas as pd

R = "/workspace/equipo5/PAULA/consejo_integrado/resultados"
OUT = "/workspace/equipo5/FIRDAOUS"
FUENTE = "https://www.lamoncloa.gob.es/multimedia/galeriasfotograficas/consejoministros/Paginas/2026/131026-rueda-prensa-consejo.aspx"

# Grupo de planos -> (persona, categoría documentada)
PERSONAS = {
    "primer_plano_A": ("sira_rego", "mujer"),
    "primer_plano_B": ("elma_saiz", "mujer"),
    "primer_plano_C": ("arcadi_espana", "hombre"),
}

pl = pd.read_csv(f"{OUT}/planos_clasificados.csv")
tr = pd.read_csv(f"{R}/resumen_tracks.csv")
ids = pd.read_csv(f"{R}/identidades_documentadas.csv", dtype=str)  # dtype=str: columnas vacías aceptan texto

# 1. Identidades: solo el track principal de cada primer plano (los demás son fondo)
for tipo, (pid, cat) in PERSONAS.items():
    tracks = pl.loc[pl["tipo"] == tipo, "track_principal"]
    m = ids["track_id"].isin(tracks)
    ids.loc[m, ["persona_id", "categoria_documentada", "fuente", "tipo_presencia", "confirmado"]] = \
        [pid, cat, FUENTE, "compareciente", "si"]
ids.to_csv(f"{OUT}/identidades_documentadas.csv", index=False)
print("Tracks confirmados:", (ids["confirmado"] == "si").sum())

# 2. Métricas por persona
t = tr.merge(ids, on="track_id")
conf = t[t["confirmado"] == "si"]
util = pl.loc[pl["tipo"] != "excluir", "dur_s"].sum()   # emisión sin espera ni cierre

personas = (conf.groupby(["persona_id", "categoria_documentada"])
              .agg(tiempo_s=("tiempo_detectado_s", "sum"),
                   planos=("plano", "nunique"),
                   area_media_pct=("area_media_pct", "mean"))
              .reset_index())
personas["pct_primeros_planos"] = 100 * personas["tiempo_s"] / personas["tiempo_s"].sum()
personas["pct_emision_util"] = 100 * personas["tiempo_s"] / util
personas.round(1).to_csv(f"{OUT}/personas_confirmadas.csv", index=False)
print(f"\nEmisión útil: {util:.0f} s\n")
print(personas.round(1).to_string(index=False))

# 3. Métricas por género, comparadas con el reparto de comparecientes
g = personas.groupby("categoria_documentada").agg(tiempo_s=("tiempo_s", "sum"), personas=("persona_id", "count"))
g["pct_tiempo"] = 100 * g["tiempo_s"] / g["tiempo_s"].sum()
g["pct_personas"] = 100 * g["personas"] / g["personas"].sum()
g["indice_paridad"] = g["pct_tiempo"] / g["pct_personas"]   # 1 = tiempo proporcional a su presencia
g.round(2).to_csv(f"{OUT}/metricas_genero.csv")
print("\n", g.round(2).to_string())

# 4. Reparto del tiempo por tipo de plano
tipos = pl[pl["tipo"] != "excluir"].groupby("tipo")["dur_s"].sum()
print("\n", (100 * tipos / util).round(1).to_string())