# Backend mínimo FastAPI para login (Render)

## Arquivos criados
- `main.py`: API com health check e login fixo.
- `requirements.txt`: dependências.
- `Procfile`: comando de start para Render (`uvicorn main:app --host 0.0.0.0 --port $PORT`).

## Endpoints
- `GET /api/health` -> `{"ok": true}`
- `POST /api/auth/login` -> body `{ "email": "admin@eagl.com.br", "password": "123456" }`
  - Se correto, retorna `{"token": "...", "user": {...}}`
  - Se errado, `401 Credenciais inválidas`

## Como publicar no Render (GUI)
1. Faça login em https://render.com.
2. Clique em **New** -> **Web Service**.
3. Conecte seu repositório Git (GitHub/GitLab) onde está esta pasta `fastapi-backend/`.
4. Escolha o branch que contém estes arquivos.
5. Preencha:
   - **Name**: `eagl-fastapi` (exemplo).
   - **Root Directory**: `fastapi-backend` (importante para pegar os arquivos certos).
   - **Environment**: `Python`.
   - **Build Command**: `pip install -r requirements.txt`.
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
6. Clique em **Create Web Service**.
7. Aguarde o deploy. Quando terminar, copie a URL pública (ex.: `https://eagl-fastapi.onrender.com`).

## Configurar o frontend
1. Edite `frontend/.env.production` e coloque:
   ```
   VITE_API_BASE_URL=https://SUA-URL-DO-RENDER/api
   ```
   Exemplo: `https://eagl-fastapi.onrender.com/api`
2. Rebuild e deploy do app:
   ```
   npm run build:app
   firebase deploy --only hosting:app
   ```

## Observação de CORS
- `main.py` já libera CORS para `https://app.eagl.com.br` e para `localhost:5173` (dev).
- Se precisar de outra origem, adicione na lista `ALLOWED_ORIGINS` em `main.py`.
