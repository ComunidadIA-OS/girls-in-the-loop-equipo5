import os
import pandas as pd

R = "/workspace/equipo5/PAULA/consejo_integrado/resultados"
OUT = "/workspace/equipo5/FIRDAOUS"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220, "display.max_colwidth", 90)

# 1. Rótulos: qué textos aparecen, cuánto tiempo y en qué planos
ev = pd.read_csv(f"{R}/eventos_texto.csv")
ev["dur"] = ev.fin_s - ev.inicio_s
textos = (ev.groupby("texto")
            .agg(dur_s=("dur", "sum"), veces=("plano", "size"),
                 planos=("plano", lambda s: sorted(set(s))))
            .sort_values("dur_s", ascending=False))
textos = textos[textos.dur_s >= 2]
textos.to_csv(f"{OUT}/textos_rotulos.csv")
print("=== TEXTOS EN PANTALLA (≥ 2 s) ===")
print(textos.head(60).to_string())

# 2. Resumen por plano: track principal y rótulos de ese plano
pl = pd.read_csv(f"{R}/planos.csv")
tr = pd.read_csv(f"{R}/resumen_tracks.csv")
tr["peso"] = tr.tiempo_detectado_s * tr.area_media_pct

filas = []
for _, p in pl.iterrows():
    t = tr[tr.plano == p.plano]
    principal = t.loc[t.peso.idxmax()] if len(t) else None
    rot = (ev[(ev.plano == p.plano) & (ev.dur >= 1)]
             .groupby("texto").dur.sum().sort_values(ascending=False).head(3))
    filas.append({
        "plano": p.plano,
        "inicio_s": round(p.inicio_s, 1),
        "dur_s": round(p.fin_s - p.inicio_s, 1),
        "n_tracks": len(t),
        "track_principal": principal.track_id if principal is not None else "",
        "area_%": round(principal.area_media_pct, 1) if principal is not None else "",
        "central": round(principal.centralidad_horizontal, 2) if principal is not None else "",
        "rotulos": " || ".join(rot.index),
    })
res = pd.DataFrame(filas)
res.to_csv(f"{OUT}/resumen_planos.csv", index=False)
print("\n=== RESUMEN POR PLANO ===")
print(res.to_string(index=False))