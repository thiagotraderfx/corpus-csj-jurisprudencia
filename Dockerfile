FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt
COPY *.py *.json ./
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
