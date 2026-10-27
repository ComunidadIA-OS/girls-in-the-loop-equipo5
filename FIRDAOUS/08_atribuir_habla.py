import pandas as pd

OUT = "/workspace/equipo5/FIRDAOUS"
NOMBRES = {"primer_plano_A": "sira_rego", "primer_plano_B": "elma_saiz", "primer_plano_C": "arcadi_espana"}
GENERO = {"sira_rego": "mujer", "elma_saiz": "mujer", "arcadi_espana": "hombre"}
OTROS = {"plano_medio": "sala_periodistas", "plano_general": "sin_atribuir", "excluir": "excluir"}

pal = pd.read_csv(f"{OUT}/transcripcion_palabras.csv").sort_values("inicio_s")
pl = pd.read_csv(f"{OUT}/planos_clasificados.csv").sort_values("inicio_s")
pal["dur"] = pal["fin_s"] - pal["inicio_s"]

# merge_asof: a cada palabra le asigna el último plano que empezó antes que ella
pal = pd.merge_asof(pal, pl[["plano", "inicio_s", "tipo"]].rename(columns={"inicio_s": "plano_ini"}),
                    left_on="inicio_s", right_on="plano_ini", direction="backward")
pal["hablante"] = pal["tipo"].map(lambda t: NOMBRES.get(t, OTROS.get(t, "sin_atribuir")))
pal.to_csv(f"{OUT}/palabras_atribuidas.csv", index=False)

# 1. Tiempo de palabra por hablante
res = (pal[pal["hablante"] != "excluir"]
       .groupby("hablante").agg(palabras=("palabra", "count"), tiempo_habla_s=("dur", "sum"))
       .sort_values("tiempo_habla_s", ascending=False))
res["pct_habla"] = 100 * res["tiempo_habla_s"] / res["tiempo_habla_s"].sum()
print(res.round(1).to_string(), "\n")

# 2. Validación: ¿cuánto del tiempo en primer plano hay voz?
pp = pd.read_csv(f"{OUT}/personas_confirmadas.csv").set_index("persona_id")
comp = res.join(pp["tiempo_s"].rename("tiempo_primer_plano_s"), how="inner")
comp["pct_plano_con_voz"] = 100 * comp["tiempo_habla_s"] / comp["tiempo_primer_plano_s"]
print(comp.round(1).to_string(), "\n")

# 3. Tiempo de palabra por género (solo comparecientes)
g = comp.assign(genero=comp.index.map(GENERO)).groupby("genero")[["palabras", "tiempo_habla_s"]].sum()
g["pct_habla"] = 100 * g["tiempo_habla_s"] / g["tiempo_habla_s"].sum()
print(g.round(1).to_string())

res.round(2).to_csv(f"{OUT}/metricas_habla.csv")
g.round(2).to_csv(f"{OUT}/metricas_habla_genero.csv")