from pathlib import Path
import os, sys, subprocess, json, traceback
root=Path(__file__).resolve().parent
lock=(root/'proceso.lock').open('a+')
try:
    if os.name=='nt':
        import msvcrt
        lock.seek(0); lock.write('0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except OSError:
    raise RuntimeError('Ya hay un análisis ejecutándose en esta carpeta.')
try:
    (root/'FALLO.txt').unlink(missing_ok=True)
    env=root/'entorno'
    python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(env)],check=True)
    ready=env/'preparado.json'
    requirements=['ultralytics>=8.3.0,<9','scenedetect==0.6.6','easyocr==1.7.2','lap>=0.5.12','pandas>=2,<4','pyyaml>=6,<7']
    if not ready.exists():
        print('Preparando entorno separado. La primera vez requiere internet.',flush=True)
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',*requirements],check=True)
        ready.write_text(json.dumps(requirements))
    config=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'config.json'
    subprocess.run([str(python),'-u',str(root/'analizar_consejo.py'),str(config)],check=True)
except BaseException:
    (root/'FALLO.txt').write_text(traceback.format_exc(),encoding='utf-8')
    raise
finally:
    pidfile=root/'proceso.json'
    if pidfile.exists():
        try:
            if json.loads(pidfile.read_text())['pid']==os.getpid():
                pidfile.unlink()
        except (OSError,ValueError,KeyError):
            pass
    lock.close()
