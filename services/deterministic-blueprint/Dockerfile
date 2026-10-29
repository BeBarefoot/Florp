FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-heb && rm -rf /var/lib/apt/lists/*
WORKDIR /service
COPY services/deterministic-blueprint/requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api/app/deterministic_blueprint /service/app/deterministic_blueprint
RUN touch /service/app/__init__.py && useradd --create-home --uid 10001 florp
USER florp
EXPOSE 8010
CMD ["uvicorn", "app.deterministic_blueprint.service:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
