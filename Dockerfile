# WPRecover API — imagen Docker para Render.
# WeasyPrint (usado por FullProjectReport) necesita libs de sistema (Pango,
# GDK-PixBuf, libffi) que el buildpack Python nativo de Render no provee; por eso
# el servicio corre como runtime Docker.
FROM python:3.12-slim-bookworm

# Libs de sistema requeridas por WeasyPrint en runtime + fuentes para el render.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias primero para aprovechar la caché de capas.
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El código de la API vive en api/ → se copia su contenido a /app.
COPY api/ .

# Render inyecta $PORT; localmente cae a 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
