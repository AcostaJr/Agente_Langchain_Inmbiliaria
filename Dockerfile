# syntax=docker/dockerfile:1
# ============================================================
# Imagen de despliegue — Canal Chatwoot (main_chatwoot.py)
# FastAPI + uvicorn. Construir desde la RAÍZ del proyecto:
#   docker build -t <tu-usuario>/app-langchain-agente-inmobiliaria:latest .
# ============================================================

# Base ligera con Python 3.11 (el proyecto requiere 3.11+ por zoneinfo)
FROM python:3.11-slim

# Buenas prácticas en contenedor: sin .pyc y logs sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Dependencias primero → aprovecha la caché de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código de la aplicación (respeta .dockerignore: NO copia .env ni credentials)
COPY . /app

# Usuario no root (seguridad)
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Puerto del servidor uvicorn (ver main_chatwoot.py)
EXPOSE 8000

# Chequeo de salud contra el endpoint /health del servicio
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Arranque del canal Chatwoot (webhook FastAPI)
CMD ["uvicorn", "main_chatwoot:app", "--host", "0.0.0.0", "--port", "8000"]
