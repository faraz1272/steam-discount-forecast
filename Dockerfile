# ---- base image ----
    FROM python:3.11-slim AS base

    # System deps (OpenMP for lightgbm; tz for correct logs)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 tzdata ca-certificates \
     && rm -rf /var/lib/apt/lists/*
    
    # Set UTF-8, timezone, and app dir
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        PORT=8080 \
        TZ=UTC
    
    WORKDIR /app
    
    # ---- install requirements first (better cache) ----
    COPY requirements.txt /app/requirements.txt
    RUN pip install --upgrade pip && \
        pip install -r /app/requirements.txt && \
        pip install uvicorn[standard] fastapi jinja2
    
    # ---- copy code ----
    # Copy only what the app needs (adjust paths if yours differ)
    COPY src/ /app/src
    COPY artifacts/ /app/artifacts
    # If your templates live under src/steam_sale/api/templates they’re already included via /app/src
    # but we’ll keep this in case you have a top-level templates folder:
    # COPY src/steam_sale/api/templates /app/src/steam_sale/api/templates
    
    # Create a non-root user for security
    RUN useradd -m appuser
    USER appuser
    
    # Expose for local clarity (Cloud Run ignores EXPOSE but it’s helpful)
    EXPOSE 8080
    
    # ---- start server ----
    # NOTE: keep module path aligned with your app location
    # Your FastAPI app is `src/steam_sale/api/main.py`, variable `app`
    CMD ["uvicorn", "src.steam_sale.api.main:app", "--host", "0.0.0.0", "--port", "8080"]