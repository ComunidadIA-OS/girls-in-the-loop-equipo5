# Girls in the Loop · Protagonismo por género en las ruedas de prensa del Consejo de Ministros

*Open-source AI project for analyzing female representation and prominence in audiovisual content using computer vision, person detection, tracking, OCR, and explainable metrics.*

**Equipo 5:** Firdaous, Noa y Paula.

## Pregunta

En una rueda de prensa del Consejo de Ministros, ¿quién ocupa la pantalla y quién tiene la palabra? ¿Ese protagonismo es proporcional a cuántas mujeres y hombres comparecen?

Medimos, por persona y por género: tiempo en pantalla, tiempo de voz, número y duración de intervenciones, quién abre y cierra, y el reparto entre la exposición inicial y el turno de preguntas.

## Resultado: rueda de prensa del 13/10/2026

Fuente: [La Moncloa](https://www.lamoncloa.gob.es/multimedia/galeriasfotograficas/consejoministros/Paginas/2026/131026-rueda-prensa-consejo.aspx). 40,6 min de emisión útil. Comparecen Elma Saiz (portavoz), Sira Rego y Arcadi España.

| | % personas | % pantalla | % voz | Paridad pantalla | Paridad voz |
|---|---:|---:|---:|---:|---:|
| Mujeres (2) | 66,7 | 77,1 | 76,7 | 1,16 | 1,15 |
| Hombres (1) | 33,3 | 22,9 | 23,3 | 0,69 | 0,70 |

*Paridad = % obtenido / % de personas. 1 = proporcional; > 1 = sobrerrepresentación.*

- En esta rueda las mujeres tienen **más protagonismo del que les correspondería por número**: ambas métricas, pantalla y voz, coinciden.
- Sira Rego es quien más habla (33 % de la voz, intervenciones de 2 min de media). Elma Saiz, como portavoz, abre y cierra, e interviene más veces (10) pero en turnos más cortos.
- Con un solo vídeo y tres personas, esto describe **esta** rueda de prensa, no una tendencia.

Informe completo con gráficos: [FIRDAOUS/salidas/consejo_131026/informe.md](FIRDAOUS/salidas/consejo_131026/informe.md)

![Línea de tiempo](FIRDAOUS/salidas/consejo_131026/graficos/2_linea_tiempo.png)

## Cómo funciona

```
vídeo .mp4
  │
  ▼  PAULA/consejo_integrado/analizar_consejo.py          (GPU)
  │  cortes de plano (PySceneDetect) · personas (YOLO11m + ByteTrack, reiniciado en cada plano)
  │  rótulos en pantalla (EasyOCR) · tiempos reales verificados con ffprobe
  │
  ▼  FIRDAOUS/pipeline.py CONFIG revisar
  │  clasifica cada plano: primer plano / plano medio (sala) / plano general / excluir
  │  asigna cada primer plano a un grupo según el rótulo OCR
  │  → carpeta revision/ con una imagen por plano
  │
  ▼  REVISIÓN HUMANA: se completa persona y categoría de cada grupo en el config,
  │  con una fuente pública (La Moncloa). El género NO se infiere de la imagen.
  │
  ▼  FIRDAOUS/pipeline.py CONFIG metricas                  (GPU para Whisper)
  │  transcripción con marcas por palabra (faster-whisper large-v3)
  │  cada palabra se atribuye a quien está en primer plano en ese instante
  │  → métricas por persona, por género, por fase
  │
  ▼  FIRDAOUS/pipeline.py CONFIG informe                   (sin GPU)
     → informe.md + graficos/
```

### Decisiones de diseño

- **Las categorías de género son documentadas, no inferidas.** El sistema final no estima el género a partir de caras: es poco fiable y éticamente problemático. Una persona revisa los planos y asigna identidad y categoría con fuente pública. Un prototipo inicial probó la estimación automática con DeepFace (`PAULA/prueba_imagen.ipynb`, `PAULA/resultados/genero_*`) y se descartó por este motivo; se conserva como registro del proceso.
- **Tracks por plano.** El seguimiento se reinicia en cada corte para que una identidad nunca "salte" entre tomas distintas.
- **Atribución de voz por plano.** Se asume que en un primer plano habla quien aparece. La voz durante planos de la sala se cuenta como "sala"; durante planos generales, como "sin atribuir".
- **Reproducibilidad.** La fase de visión guarda la huella SHA-256 del vídeo, del código y de los pesos, y las versiones de cada librería; se niega a mezclar resultados si algo cambia.

## Interfaz

En Windows: doble clic en `ABRIR_INTERFAZ.bat` desde el explorador de archivos. En cualquier sistema:

```bash
pip install streamlit plotly pandas matplotlib tabulate   # solo ver resultados
pip install -r requirements.txt                           # también analizar vídeos (GPU)
streamlit run app.py
```

| Pestaña | Qué hace |
|---|---|
| 📊 Resultados | Indicadores de paridad, gráficos interactivos, tabla por persona, transcripción por turnos con filtro por hablante y búsqueda, descargas |
| ⚙️ Nuevo análisis / continuar | Sube un vídeo desde el navegador y llévalo por los 4 pasos (visión → quién es quién → métricas → informe), con estado 🕒/⏳/✅/❌ y registro de cada proceso |
| ⚖️ Comparar | Índice de paridad de las ruedas de prensa que puedes ver |

Pensada para que varias personas la usen a la vez en un servidor con GPU:

- **Cola de trabajos** (`cola.py`): los pasos pesados se ejecutan de uno en uno para no saturar la GPU. Cada persona ve cuántos trabajos tiene por delante y puede cerrar la página y volver; si el servidor se reinicia, la cola se retoma.
- **Análisis privados:** cada análisis nuevo recibe un código y solo se ve con el enlace que lo contiene (`?a=CÓDIGO`) o escribiendo el código en la barra lateral. El análisis del 13/10 es público.
- **Sin GPU** (un portátil) se pueden ver resultados, reclasificar planos y regenerar informes; la app desactiva los pasos que la máquina no puede ejecutar.

### Publicarla con GPU (OVHcloud AI Deploy)

El `Dockerfile` empaqueta la app con FFmpeg y todas las dependencias.

```bash
docker build -t <registro>/girls-in-the-loop:1 .
docker push <registro>/girls-in-the-loop:1
ovhai app run <registro>/girls-in-the-loop:1 --gpu 1 --default-http-port 8080 --unsecure-http
```

`--unsecure-http` hace que el enlace sea accesible sin cuenta de OVH. Comprueba las opciones con `ovhai app run --help`. Los archivos del contenedor se pierden si la app se reinicia; para conservar vídeos y resultados hay que montar un volumen de Object Storage en `/workspace`. Una GPU encendida consume créditos por hora.

## Reproducir desde la terminal

Requisitos: Python 3.10–3.13, FFmpeg, GPU CUDA para visión y transcripción. Probado en una VM de OVHcloud AI Notebooks. Las rutas de los config son relativas a la carpeta `equipo5`.

```bash
# 1. Visión
python PAULA/consejo_integrado/preparar_y_ejecutar.py [CONFIG_VISION.json]

# 2. Métricas
python FIRDAOUS/pipeline.py FIRDAOUS/config_131026.json revisar
#    → revisa salidas/.../revision/ y completa "persona", "nombre" y "categoria" de cada grupo
python FIRDAOUS/pipeline.py FIRDAOUS/config_131026.json metricas
python FIRDAOUS/pipeline.py FIRDAOUS/config_131026.json informe
```

Sin GPU, Whisper se ejecuta en CPU (mucho más lento; conviene `"modelo_whisper": "small"`).

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `app.py`, `cola.py` | **Interfaz** (Streamlit) y cola de trabajos |
| `Dockerfile` | Imagen para publicarla con GPU |
| `PAULA/consejo_integrado/` | **Fase de visión final** (motor, config y resultados) |
| `FIRDAOUS/pipeline.py`, `FIRDAOUS/config_131026.json` | **Fase de métricas e informe final** |
| `FIRDAOUS/salidas/consejo_131026/` | **Resultados finales**: métricas CSV, transcripción, informe y gráficos |
| `NOA/` | Prototipos: cortes de plano y detección/seguimiento, pruebas de modelos |
| `PAULA/*.ipynb`, `PAULA/resultados/` | Prototipos: OCR y pruebas sobre fragmentos |
| `FIRDAOUS/01_…08_*.py` y CSV sueltos | Prototipos paso a paso, sustituidos por `pipeline.py` |

## Limitaciones

- **Precisión no validada todavía.** La clasificación automática de planos no se ha comparado con una anotación manual (plantilla en `FIRDAOUS/anotacion_manual.csv`, pendiente de completar).
- **Un solo vídeo.** Las conclusiones no se pueden generalizar.
- **Atribución de voz aproximada.** Si quien habla no está en pantalla (p. ej. responde mientras se ve la sala), la palabra se atribuye mal. El 12,3 % de la voz queda sin atribuir. Una mejora sería la diarización de hablantes.
- **Rótulos OCR ruidosos** (p. ej. "VLIRA" por "Sira Rego"); los grupos se definen por el texto que el OCR devuelve realmente.
- **Turno de preguntas** = primer plano de la sala de prensa; es una heurística.
- **Categoría binaria** limitada a lo que documenta la fuente pública.

## Modelos y licencias

| Componente | Uso | Licencia |
|---|---|---|
| Ultralytics YOLO11m | detección de personas | AGPL-3.0 |
| ByteTrack (vía Ultralytics) | seguimiento | MIT / AGPL-3.0 (Ultralytics) |
| PySceneDetect | cortes de plano | BSD-3-Clause |
| EasyOCR | rótulos | Apache-2.0 |
| faster-whisper + Whisper large-v3 | transcripción | MIT |
| FFmpeg | audio y tiempos | LGPL/GPL |
| pandas, NumPy, matplotlib | análisis y gráficos | BSD / PSF-compatible |
| Streamlit, Plotly | interfaz | Apache-2.0 / MIT |

**Licencia del proyecto: AGPL-3.0** (ver `LICENSE`), porque Ultralytics YOLO es AGPL-3.0 y exige esa licencia al sistema que lo usa. Para publicarlo con una licencia permisiva (MIT) habría que sustituir el detector, p. ej. por Faster R-CNN de torchvision (BSD-3), ya probado en `PAULA/prueba_imagen.ipynb`.

El vídeo es material público de La Moncloa y no se redistribuye en el repositorio.
