# Imagen para publicar la interfaz con GPU en OVHcloud AI Deploy.
# Construir:  docker build -t girls-in-the-loop .
FROM python:3.12-slim

# FFmpeg (audio y tiempos del vídeo) y librerías de sistema que necesita OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# AI Deploy ejecuta el contenedor con el usuario 42420
RUN chown -R 42420:42420 /workspace
ENV HOME=/workspace

EXPOSE 8080
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
