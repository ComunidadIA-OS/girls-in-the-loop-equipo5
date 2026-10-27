import os
import shutil
import pandas as pd

R = "/workspace/equipo5/PAULA/consejo_integrado/resultados"
OUT = "/workspace/equipo5/FIRDAOUS"

res = pd.read_csv(f"{OUT}/resumen_planos.csv")
res["rotulos"] = res["rotulos"].fillna("")

# Reglas sacadas de los datos: los primeros planos tienen pocas personas
# y ocupan mucha pantalla; los generales, muchas personas pequeñas.
def clasificar(f):
    if f["plano"] in (0, 64) or f["n_tracks"] == 0:
        return "excluir"
    if f["n_tracks"] <= 3 and f["area_%"] >= 25:
        if "VLIRA" in f["rotulos"]:
            return "primer_plano_A"
        if "RLVS" in f["rotulos"]:
            return "primer_plano_B"
        return "primer_plano_C"
    if f["area_%"] >= 15:
        return "plano_medio"
    return "plano_general"

res["tipo"] = res.apply(clasificar, axis=1)
res.to_csv(f"{OUT}/planos_clasificados.csv", index=False)
print(res.groupby("tipo").agg(planos=("plano", "count"), dur_s=("dur_s", "sum")).round(1))

# Un recorte del track principal de cada plano, separado por grupo
rec = pd.read_csv(f"{R}/recortes.csv")
for _, f in res[res["tipo"] != "excluir"].iterrows():
    r = rec[rec["track"] == f["track_principal"]]
    if r.empty:
        continue
    fila = r.iloc[len(r) // 2]  # el del medio, suele ser el más estable
    destino = f"{OUT}/revision/{f['tipo']}"
    os.makedirs(destino, exist_ok=True)
    nombre = f"plano{int(f['plano']):02d}_{os.path.basename(fila['path'])}"
    shutil.copy(f"{R}/{fila['path']}", f"{destino}/{nombre}")

print("\nRecortes copiados en", f"{OUT}/revision")