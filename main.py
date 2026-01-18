from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="EAGL Minimal API", version="0.1.0")

# Ajuste aqui a origem permitida do frontend em produção
ALLOWED_ORIGINS = [
    "https://app.eagl.com.br",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    email: str
    password: str


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    password = payload.password.strip()

    # Usuário fixo para teste
    if email == "admin@eagl.com.br" and password == "123456":
        return {"token": "token-admin-123456", "user": {"email": email, "role": "admin"}}

    raise HTTPException(status_code=401, detail="Credenciais inválidas")
