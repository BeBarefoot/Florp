# Technical direction

Local development uses Next.js 14, React, inline SVG overlay editing, React Three Fiber, FastAPI, Pydantic, SQLModel/SQLite and local disk storage. The future geometry source of truth is a shared wall/opening graph plus room polygons, with observation/inference provenance. All generated images will reference immutable geometry, design and camera versions. Extractor is a pluggable OpenAI-compatible endpoint and will be supplemented with PyMuPDF/OpenCV/OCR evidence. The first milestone does not implement the full extraction pipeline. No model training is done without reviewed annotations and a held-out evaluation set.

API: GET /health, GET/POST /projects, GET/POST /projects/:id/blueprints, GET /blueprints/:id/preview, GET/POST /blueprints/:id/layout, POST /blueprints/:id/extract. Future rendering route deliberately returns 501 until functional.
