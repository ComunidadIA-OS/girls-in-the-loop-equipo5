import pandas as pd

OUT = "/workspace/equipo5/FIRDAOUS"
NOMBRES = {"primer_plano_A": "sira_rego", "primer_plano_B": "elma_saiz", "primer_plano_C": "arcadi_espana"}

pl = pd.read_csv(f"{OUT}/planos_clasificados.csv")
pl = pl[pl["tipo"] != "excluir"]

an = pd.DataFrame({
    "plano": pl["plano"].astype(int),
    "tipo_automatico": pl["tipo"],
    "persona_automatica": pl["tipo"].map(NOMBRES).fillna(""),
})
# Primeros planos: ya revisados por ti, todos correctos
es_cp = an["tipo_automatico"].isin(NOMBRES)
an["persona_revisada"] = an["persona_automatica"].where(es_cp, "")
an["correcto"] = ["si" if c else "" for c in es_cp]
# Planos medios y generales: pendiente comprobar si sale algún compareciente
an["hay_compareciente"] = ["" if not c else "-" for c in es_cp]
an["revisado_por"] = ["firdaous" if c else "" for c in es_cp]
an["notas"] = ""

an.to_csv(f"{OUT}/anotacion_manual.csv", index=False)
print(an["tipo_automatico"].value_counts())