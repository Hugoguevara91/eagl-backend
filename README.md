# EAGL FastAPI Backend

Backend FastAPI preparado para Cloud Run (e execução local via Uvicorn).

## Estrutura
- `main.py` é o ponto de entrada com `app = FastAPI()` e rota `GET /api/health`.
- `requirements.txt` lista dependências mínimas.
- `Dockerfile` pronto para Cloud Run (usa `$PORT`, bind `0.0.0.0`).

## Rodar local
```bash
cd fastapi-backend
python -m venv .venv
. .venv/Scripts/activate   # ou source .venv/bin/activate no Linux/Mac
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints úteis:
- Saúde: `GET /api/health` retorna `{"status": "ok"}`.
- Docs interativas: `/api/docs` (Swagger) e `/api/redoc`.

## Bulk import/export
Principais rotas:
- `GET  /api/bulk/templates/{entity}`
- `POST /api/bulk/import/{entity}/upload`
- `POST /api/bulk/import/{job_id}/validate`
- `POST /api/bulk/import/{job_id}/confirm`
- `GET  /api/bulk/import/{job_id}`
- `GET  /api/bulk/import`
- `GET  /api/bulk/import/{job_id}/errors`
- `GET  /api/bulk/import/{job_id}/download-errors`
- `GET  /api/bulk/export/{entity}`
- `GET  /api/bulk/export/jobs`
- `GET  /api/bulk/export/jobs/{job_id}`

Config:
- `LOCAL_STORAGE=1` + `LOCAL_STORAGE_DIR=storage` (local)
- `GCS_BUCKET` (producao)
- `BULK_MAX_FILE_MB` e `BULK_EXPORT_SYNC_LIMIT`
- Cloud Tasks: `GCP_PROJECT_ID`, `CLOUD_TASKS_LOCATION`, `CLOUD_TASKS_QUEUE`, `CLOUD_TASKS_WORKER_URL`, `BULK_TASKS_SECRET`
