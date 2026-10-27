"""Motor del notebook. Usar iniciar_consejo.py o la celda única del notebook."""
from pathlib import Path
import csv
import hashlib
import html
import json
import math
import sqlite3
import subprocess
import sys
import time
import traceback


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def frame_times(video, fps, total):
    """Preferir PTS reales; no convertir silenciosamente VFR en tiempo nominal."""
    import shutil
    if not shutil.which('ffprobe'):
        raise RuntimeError('Falta ffprobe (FFmpeg). Es necesario para verificar los tiempos del vídeo.')
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'frame=best_effort_timestamp_time,pkt_duration_time',
                        '-of', 'json', str(video)], capture_output=True, text=True, check=True)
    records = json.loads(p.stdout)['frames']
    ts = [float(r['best_effort_timestamp_time']) for r in records]
    if not ts or any(not math.isfinite(x) for x in ts):
        raise RuntimeError('Marcas temporales no válidas.')
    if any(b <= a for a, b in zip(ts, ts[1:])):
        raise RuntimeError('PTS duplicados o no crecientes: normaliza el vídeo antes del análisis.')
    offset = ts[0]
    ts = [t - offset for t in ts]
    tail = float(records[-1].get('pkt_duration_time', 0))
    if tail <= 0:
        tail = ts[-1] - ts[-2] if len(ts) > 1 else 1 / fps
    if abs(len(ts) - total) > 1:
        raise RuntimeError(f'OpenCV declara {total} fotogramas y ffprobe encuentra {len(ts)}. Revisar vídeo.')
    return ts + [ts[-1] + tail]


def selected_frames(start, end, timestamps, rate):
    """Muestrear por tiempo real, incluyendo el primer frame de cada plano."""
    chosen, target = [], timestamps[start]
    for i in range(start, end):
        if timestamps[i] + 1e-8 >= target:
            chosen.append(i)
            target = timestamps[i] + 1 / rate
    return chosen


def init_db(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS done(scene INTEGER PRIMARY KEY, seconds REAL);
    CREATE TABLE IF NOT EXISTS frames(
      scene INTEGER, frame INTEGER PRIMARY KEY, t REAL, dt REAL,
      n INTEGER, text TEXT, ocr_t REAL);
    CREATE TABLE IF NOT EXISTS det(
      scene INTEGER, frame INTEGER, track TEXT, t REAL, dt REAL,
      conf REAL, x1 REAL, y1 REAL, x2 REAL, y2 REAL,
      area REAL, centrality REAL, border INTEGER,
      PRIMARY KEY(frame, track));
    CREATE TABLE IF NOT EXISTS ocr(
      scene INTEGER, frame INTEGER, t REAL, blocks TEXT,
      PRIMARY KEY(frame));
    CREATE TABLE IF NOT EXISTS crops(
      track TEXT, frame INTEGER, t REAL, path TEXT,
      PRIMARY KEY(track, frame));
    ''')
    db.commit()


def export_results(db, out, cfg, duration):
    import pandas as pd
    frames = pd.read_sql_query('SELECT * FROM frames ORDER BY frame', db)
    det = pd.read_sql_query('SELECT * FROM det ORDER BY frame,track', db)
    ocr = pd.read_sql_query('SELECT * FROM ocr ORDER BY frame', db)
    crops = pd.read_sql_query('SELECT * FROM crops ORDER BY track,frame', db)
    frames.to_csv(out / 'linea_tiempo.csv', index=False)
    det.to_csv(out / 'detecciones.csv', index=False)
    ocr.to_csv(out / 'ocr_crudo.csv', index=False)
    crops.to_csv(out / 'recortes.csv', index=False)
    rows = []
    for tid, group in det.groupby('track'):
        rows.append(dict(track_id=tid, plano=int(group.scene.iloc[0]),
                         inicio_s=group.t.min(), fin_intervalo_s=(group.t + group.dt).max(),
                         muestras=len(group), tiempo_detectado_s=group.dt.sum(),
                         area_media_pct=group.area.mean(), centralidad_horizontal=group.centrality.mean(),
                         fraccion_borde=group.border.mean(), confianza_media=group.conf.mean(),
                         revisar_corto=group.dt.sum() < 0.5,
                         fraccion_area_menor_1pct=(group.area < 1).mean(),
                         tiempo_area_mayor_8pct_s=group.loc[group.area > 8, 'dt'].sum()))
    summary = pd.DataFrame(rows, columns=['track_id','plano','inicio_s','fin_intervalo_s',
        'muestras','tiempo_detectado_s','area_media_pct','centralidad_horizontal',
        'fraccion_borde','confianza_media','revisar_corto','fraccion_area_menor_1pct',
        'tiempo_area_mayor_8pct_s'])
    summary.to_csv(out / 'resumen_tracks.csv', index=False)
    # Etiquetas humanas: nunca deducir categorías sensibles de la apariencia.
    label_path = out / 'identidades_documentadas.csv'
    label_cols = ['track_id','persona_id','categoria_documentada','fuente','tipo_presencia','confirmado']
    labels = pd.read_csv(label_path, dtype=str, keep_default_na=False) if label_path.exists() else pd.DataFrame(columns=label_cols)
    if any(c not in labels for c in label_cols) or labels.track_id.duplicated().any():
        raise ValueError('La tabla de identidades tiene columnas ausentes o tracks duplicados.')
    missing = sorted(set(summary.track_id) - set(labels.track_id))
    extra = pd.DataFrame([dict(zip(label_cols, [tid, '', 'no_documentado', '', '', 'no'])) for tid in missing], columns=label_cols)
    labels = pd.concat([labels, extra], ignore_index=True)
    labels.to_csv(label_path, index=False)
    confirmed = labels[(labels.confirmado.str.lower() == 'si') & (labels.persona_id != '')].copy()
    bad = confirmed.groupby('persona_id').categoria_documentada.nunique()
    if (bad > 1).any():
        raise ValueError('Una persona tiene categorías documentadas incompatibles. Revisa la tabla.')
    if ((confirmed.categoria_documentada != 'no_documentado') & (confirmed.fuente == '')).any():
        raise ValueError('Las categorías documentadas requieren una fuente.')
    merged = det.merge(confirmed, left_on='track', right_on='track_id')
    # Una persona duplicada en pantalla se cuenta una vez por instante.
    unique = merged.drop_duplicates(['persona_id','frame'])
    person_rows = []
    for pid, g in unique.groupby('persona_id'):
        person_rows.append({'persona_id':pid, 'categoria_documentada':g.categoria_documentada.iloc[0],
                            'tiempo_detectado_s':g.dt.sum(), 'n_tracks':merged.loc[merged.persona_id == pid,'track'].nunique()})
    pd.DataFrame(person_rows, columns=['persona_id','categoria_documentada','tiempo_detectado_s','n_tracks']).to_csv(out / 'personas_confirmadas.csv', index=False)
    category = unique.groupby(['frame','categoria_documentada']).persona_id.nunique().unstack(fill_value=0)
    category = category.reindex(frames.frame, fill_value=0)
    category.index.name = 'frame'
    category.to_csv(out / 'conteos_categorias_documentadas.csv')
    # Eventos de texto: solo igualdad normalizada; nunca atravesar un corte.
    events = []
    for r in frames.itertuples():
        txt = ' '.join(str(r.text).split())
        if not txt:
            continue
        if events and events[-1]['plano'] == r.scene and events[-1]['texto'].casefold() == txt.casefold() and abs(events[-1]['fin_s'] - r.t) < 1e-5:
            events[-1]['fin_s'] = r.t + r.dt
        else:
            events.append(dict(plano=r.scene, inicio_s=r.t, fin_s=r.t + r.dt, texto=txt))
    pd.DataFrame(events, columns=['plano','inicio_s','fin_s','texto']).to_csv(out / 'eventos_texto.csv', index=False)
    cards = []
    for row in summary.itertuples():
        pics = crops[crops.track == row.track_id]
        images = ''.join(f'<figure><img loading="lazy" src="{html.escape(p.path, quote=True)}"><figcaption>{p.t:.2f} s</figcaption></figure>' for p in pics.itertuples())
        cards.append(f'<article><h2>{html.escape(row.track_id)}</h2><p>Plano {row.plano}; {row.tiempo_detectado_s:.2f} s detectados; revisar corto: {row.revisar_corto}</p>{images}</article>')
    (out / 'revision.html').write_text('<!doctype html><meta charset="utf-8"><title>Revisión de tracks</title><style>body{font:16px system-ui;margin:32px}article{border-top:1px solid #bbb;padding:16px}figure{display:inline-block;margin:8px}img{max-height:240px;max-width:240px}</style><h1>Tracks pendientes de revisión</h1><p>Un track no es una identidad confirmada. Revisa cortes, fragmentaciones, fotografías y ventanas superpuestas. Anota persona_id en identidades_documentadas.csv y vuelve a ejecutar para actualizar los resúmenes.</p>' + ''.join(cards), encoding='utf-8')
    total_observed = float(frames.dt.sum()) if len(frames) else 0
    report = dict(estado='completo', duracion_intervalo_s=duration, tiempo_muestreado_s=total_observed,
                  tiempo_con_tracks_s=float(frames.loc[frames.n > 0,'dt'].sum()), tracks=len(summary),
                  personas_confirmadas=len(person_rows), detecciones=len(det), muestras_ocr=len(ocr),
                  calidad_validada=False, categorias='Solo etiquetas documentadas; no inferidas de imágenes',
                  identidad='Tracks por plano; unión entre planos requiere confirmación',
                  medicion='Cada muestra representa hasta la siguiente muestra o el fin del plano. No interpola detecciones perdidas.',
                  audio='No se analiza audio ni se atribuye quién habla')
    atomic_json(out / 'resumen.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def run(cfg):
    import bisect
    import importlib.metadata as metadata
    import cv2
    import easyocr
    import torch
    import yaml
    from ultralytics import YOLO
    from scenedetect import open_video, SceneManager, ContentDetector, ThresholdDetector
    video = Path(cfg['video']).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(f'No existe el vídeo: {video}')
    out = Path(cfg['salida']).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'recortes').mkdir(exist_ok=True)
    versions = {p:metadata.version(p) for p in ['ultralytics','scenedetect','easyocr','torch','torchvision','numpy','pandas']}
    stamp = dict(config=cfg, video_sha256=fingerprint(video), versiones=versions, motor_sha256=fingerprint(Path(__file__)))
    manifest = out / 'ejecucion.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')) != stamp:
        raise RuntimeError('Han cambiado vídeo, configuración, motor o versiones. Usa otra carpeta SALIDA para no mezclar resultados.')
    atomic_json(manifest, stamp)
    subprocess.run([sys.executable,'-m','pip','freeze'], stdout=(out / 'entorno.txt').open('w', encoding='utf-8'), check=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError('OpenCV no puede abrir el vídeo.')
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if not math.isfinite(fps) or fps <= 0 or total <= 0:
        raise RuntimeError('FPS o número de fotogramas no válidos.')
    times_file = out / 'tiempos.json'
    if times_file.exists():
        timestamps = json.loads(times_file.read_text())
    else:
        print('Verificando tiempos reales del vídeo...', flush=True)
        timestamps = frame_times(video, fps, total)
        atomic_json(times_file, timestamps)
    total = len(timestamps) - 1
    lo = bisect.bisect_left(timestamps, cfg['inicio_s'])
    hi = min(total, bisect.bisect_left(timestamps, cfg['fin_s'])) if cfg['fin_s'] is not None else total
    if not 0 <= lo < hi <= total:
        raise ValueError('Intervalo fuera del vídeo o vacío.')
    scene_file = out / 'planos.json'
    if scene_file.exists():
        scenes = json.loads(scene_file.read_text())
    else:
        print('Detectando cortes de plano (primera pasada)...', flush=True)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=27, min_scene_len=max(1,round(fps * .3))))
        manager.add_detector(ThresholdDetector(threshold=12, min_scene_len=max(1,round(fps * .3))))
        source = open_video(str(video))
        manager.detect_scenes(source, show_progress=True)
        raw = manager.get_scene_list(start_in_scene=True)
        # Las escenas de PySceneDetect tienen final exclusivo.
        bounds = sorted(set([0,total] + [a.get_frames() for a,b in raw] + [b.get_frames() for a,b in raw]))
        scenes = [[max(a,lo), min(b,hi)] for a,b in zip(bounds,bounds[1:]) if max(a,lo) < min(b,hi)]
        atomic_json(scene_file, scenes)
    assert scenes[0][0] == lo and scenes[-1][1] == hi
    assert all(a[1] == b[0] for a,b in zip(scenes,scenes[1:]))
    with (out / 'planos.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['plano','frame_ini','frame_fin_exclusivo','inicio_s','fin_s'])
        w.writerows((i,a,b,timestamps[a],timestamps[b]) for i,(a,b) in enumerate(scenes))
    gpu = torch.cuda.is_available()
    if cfg.get('exigir_gpu', True) and not gpu:
        raise RuntimeError('No hay GPU CUDA disponible. Para aceptar ejecución lenta pon EXIGIR_GPU=False.')
    print('Dispositivo:', torch.cuda.get_device_name(0) if gpu else 'CPU', flush=True)
    model = YOLO(cfg['modelo'])
    model_file = Path(getattr(model,'ckpt_path',cfg['modelo']))
    if model_file.is_file():
        weights = {'path':str(model_file.resolve()),'sha256':fingerprint(model_file)}
        old_weights = out / 'pesos.json'
        if old_weights.exists() and json.loads(old_weights.read_text())['sha256'] != weights['sha256']:
            raise RuntimeError('Los pesos han cambiado; utiliza otra carpeta de salida.')
        atomic_json(old_weights, weights)
    reader = easyocr.Reader(['es','en'], gpu=gpu, model_storage_directory=str(out.parent / 'modelos_easyocr'))
    tracker = out / 'bytetrack.yaml'
    tracker.write_text(yaml.safe_dump(dict(tracker_type='bytetrack', track_high_thresh=.25,
        track_low_thresh=.1, new_track_thresh=.4, track_buffer=max(1,round(2*min(fps,cfg['muestras_s']))),
        match_thresh=.8, fuse_score=True)), encoding='utf-8')
    db = sqlite3.connect(out / 'analisis.sqlite')
    init_db(db)
    finished = {r[0] for r in db.execute('SELECT scene FROM done')}
    cap = cv2.VideoCapture(str(video))
    try:
        for sid,(start,end) in enumerate(scenes):
            if sid in finished:
                continue
            started = time.monotonic()
            last_notice = started
            print(f'Plano {sid+1}/{len(scenes)}: {timestamps[start]:.2f}–{timestamps[end]:.2f} s', flush=True)
            if getattr(model,'predictor',None) is not None:
                for tr in getattr(model.predictor,'trackers',[]):
                    tr.reset()
            selected = selected_frames(start,end,timestamps,cfg['muestras_s'])
            durations = {f:timestamps[selected[j+1] if j+1 < len(selected) else end]-timestamps[f] for j,f in enumerate(selected)}
            next_ocr, last_text, last_ocr = -1., '', None
            crop_counts, last_crop = {}, {}
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            pos = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES)))
            if pos != start:
                raise RuntimeError(f'No se pudo posicionar el vídeo en {start} (posición {pos}).')
            # Una transacción por plano: un fallo revierte el plano incompleto.
            with db:
                wanted = set(selected)
                for fi in range(start,end):
                    if not cap.grab():
                        raise RuntimeError(f'Lectura interrumpida en fotograma {fi}; plano no confirmado.')
                    if fi not in wanted:
                        continue
                    ok, frame = cap.retrieve()
                    if not ok:
                        raise RuntimeError(f'No se pudo decodificar el fotograma {fi}.')
                    t, dt = timestamps[fi], durations[fi]
                    h,w = frame.shape[:2]
                    result = model.track(frame, persist=True, tracker=str(tracker), classes=[0],
                        conf=.1, iou=.7, imgsz=cfg['imgsz'], device=0 if gpu else 'cpu', verbose=False)[0]
                    count = 0
                    if result.boxes is not None and result.boxes.id is not None:
                        for box, ident, conf in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.id.int().cpu().tolist(), result.boxes.conf.cpu().tolist()):
                            x1,y1,x2,y2 = box
                            x1,x2 = max(0.,x1),min(float(w),x2)
                            y1,y2 = max(0.,y1),min(float(h),y2)
                            if x2 <= x1 or y2 <= y1:
                                continue
                            tid = f'p{sid:05d}_t{ident:05d}'
                            area = 100*(x2-x1)*(y2-y1)/(w*h)
                            cent = 1-2*abs((x1+x2)/(2*w)-.5)
                            border = int(x1<=3 or y1<=3 or x2>=w-3 or y2>=h-3)
                            db.execute('INSERT INTO det VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                       (sid,fi,tid,t,dt,float(conf),x1,y1,x2,y2,area,cent,border))
                            count += 1
                            if crop_counts.get(tid,0)<4 and t-last_crop.get(tid,-1e9)>=2:
                                crop = frame[int(y1):math.ceil(y2),int(x1):math.ceil(x2)]
                                if crop.size:
                                    rel = f'recortes/{tid}_{fi}.jpg'
                                    if not cv2.imwrite(str(out / rel),crop):
                                        raise RuntimeError('No se pudo guardar un recorte.')
                                    db.execute('INSERT INTO crops VALUES (?,?,?,?)',(tid,fi,t,rel))
                                    crop_counts[tid] = crop_counts.get(tid,0)+1
                                    last_crop[tid] = t
                    if t + 1e-8 >= next_ocr:
                        blocks = []
                        for polygon,txt,score in reader.readtext(frame, detail=1, paragraph=False):
                            blocks.append(dict(texto=txt,confianza=float(score),
                                               poligono=[[float(x),float(y)] for x,y in polygon]))
                        blocks.sort(key=lambda x:(min(p[1] for p in x['poligono'])//20,min(p[0] for p in x['poligono'])))
                        db.execute('INSERT INTO ocr VALUES (?,?,?,?)',(sid,fi,t,json.dumps(blocks,ensure_ascii=False)))
                        last_text = ' | '.join(b['texto'] for b in blocks if b['confianza']>=cfg['conf_ocr'])
                        last_ocr = t
                        next_ocr = t + cfg['ocr_cada_s']
                    db.execute('INSERT INTO frames VALUES (?,?,?,?,?,?,?)',(sid,fi,t,dt,count,last_text,last_ocr))
                    if time.monotonic() - last_notice >= 30:
                        print(f'  Plano {sid+1}: segundo {t:.1f} / {timestamps[end]:.1f}', flush=True)
                        last_notice = time.monotonic()
                db.execute('INSERT INTO done VALUES (?,?)',(sid,time.monotonic()-started))
            atomic_json(out / 'estado.json', dict(estado='en_proceso',planos_terminados=len(finished)+1,total_planos=len(scenes),ultimo_segundo=timestamps[end]))
            finished.add(sid)
            print(f'Guardado plano {sid+1}; {time.monotonic()-started:.1f} s de cálculo', flush=True)
        export_results(db,out,cfg,timestamps[hi]-timestamps[lo])
        atomic_json(out / 'estado.json',dict(estado='completo',planos_terminados=len(finished),total_planos=len(scenes)))
    finally:
        cap.release()
        db.close()
    print('TERMINADO. Resultados:',out,flush=True)


if __name__ == '__main__':
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        run(config)
    except BaseException as exc:
        folder = Path(config['salida'])
        folder.mkdir(parents=True,exist_ok=True)
        atomic_json(folder / 'error_ultimo_intento.json',dict(error=type(exc).__name__,mensaje=str(exc),detalle=traceback.format_exc()))
        atomic_json(folder / 'estado.json',dict(estado='error',mensaje=str(exc)))
        raise
