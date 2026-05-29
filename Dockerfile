# DCR Feasibility & Compliance System — container image
FROM python:3.12-slim

WORKDIR /app

# Python deps first (cached layer). Wheels for PyMuPDF/Shapely/ezdxf/reportlab are self-contained.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + the rules knowledge base (data/text working extracts are NOT shipped)
COPY backend backend
COPY frontend frontend
COPY data/rules data/rules

ENV PYTHONUNBUFFERED=1
# DB on a persistent disk if the host provides one (see render.yaml). Falls back to /app/data.
ENV DB_PATH=/var/data/projects.db

WORKDIR /app/backend
EXPOSE 8000
# PORT is provided by the host (Render sets it); default 8000 locally.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
