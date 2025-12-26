from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="EAGL Minimal API", version="0.1.0")

# Origens permitidas (frontend)
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

# ---------- MODELS ----------

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------- ROUTES ----------

@app.get("/")
def root():
    return {
        "status": "EAGL backend online",
        "health": "/api/health",
        "login": "/api/auth/login"
    }

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    password = payload.password.strip()

    # Usuário fixo para teste
    if email == "admin@eagl.com.br" and password == "123456":
        return {
            "token": "token-admin-123456",
            "user": {
                "email": email,
                "role": "admin"
            }
        }

    raise HTTPException(status_code=401, detail="Credenciais inválidas")
