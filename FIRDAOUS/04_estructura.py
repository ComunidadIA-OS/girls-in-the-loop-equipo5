import pandas as pd

OUT = "/workspace/equipo5/FIRDAOUS"
NOMBRES = {"primer_plano_A": "sira_rego", "primer_plano_B": "elma_saiz", "primer_plano_C": "arcadi_espana"}

pl = pd.read_csv(f"{OUT}/planos_clasificados.csv")
cp = pl[pl["tipo"].isin(NOMBRES)].sort_values("plano").copy()
cp["persona"] = cp["tipo"].map(NOMBRES)

print("Abre:", cp.iloc[0]["persona"], "| Cierra:", cp.iloc[-1]["persona"])
print("Secuencia:", " → ".join(cp["persona"].str.split("_").str[0]))

est = cp.groupby("persona").agg(
    intervenciones=("plano", "count"),
    duracion_media_s=("dur_s", "mean"),
    duracion_max_s=("dur_s", "max"),
    primera_aparicion_s=("inicio_s", "min"),
).round(1)
est.to_csv(f"{OUT}/metricas_estructura.csv")
print("\n", est.to_string())
primera_pregunta = pl.loc[pl["tipo"] == "plano_medio", "inicio_s"].min()
cp["fase"] = (cp["inicio_s"] < primera_pregunta).map({True: "exposicion", False: "preguntas"})

fases = cp.pivot_table(index="persona", columns="fase", values="dur_s", aggfunc=["count", "sum"]).round(1)
fases.to_csv(f"{OUT}/metricas_fases.csv")
print(f"\nPrimera pregunta en el segundo {primera_pregunta:.0f}\n")
print(fases.to_string())