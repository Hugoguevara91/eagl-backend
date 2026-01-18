from datetime import datetime, timedelta
import hashlib
import hmac
import json
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.db.session import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
platform_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/platform/auth/token")

PLATFORM_ROLES = {
    "PLATFORM_OWNER",
    "PLATFORM_ADMIN",
    "PLATFORM_SUPPORT",
    "PLATFORM_FINANCE",
    "PLATFORM_AUDITOR",
}


def get_user_roles(db: Session, user: models.User) -> list[models.Role]:
    roles = (
        db.query(models.Role)
        .join(models.UserRole, models.UserRole.role_id == models.Role.id)
        .filter(models.UserRole.user_id == user.id)
        .all()
    )
    if roles:
        return roles
    if user.role:
        role = (
            db.query(models.Role)
            .filter(models.Role.tenant_id == user.tenant_id, models.Role.nome == user.role)
            .first()
        )
        if role:
            return [role]
    return []


def get_user_permissions(db: Session, user: models.User) -> set[str]:
    roles = get_user_roles(db, user)
    role_ids = [role.id for role in roles]
    permissions: set[str] = set()
    if role_ids:
        perms = (
            db.query(models.Permission.code)
            .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
            .filter(models.RolePermission.role_id.in_(role_ids))
            .all()
        )
        permissions.update(code for (code,) in perms)

    overrides = (
        db.query(models.UserPermission, models.Permission.code)
        .join(models.Permission, models.Permission.id == models.UserPermission.permission_id)
        .filter(models.UserPermission.user_id == user.id)
        .all()
    )
    denied = {code for override, code in overrides if override.mode == "deny"}
    granted = {code for override, code in overrides if override.mode == "grant"}
    permissions.difference_update(denied)
    permissions.update(granted)
    return permissions


def get_user_scope(db: Session, user: models.User) -> dict[str, list[str]]:
    scope_entries = (
        db.query(models.UserScope)
        .filter(models.UserScope.user_id == user.id)
        .all()
    )
    scope = {"clients": [], "sites": [], "contracts": []}
    for entry in scope_entries:
        if entry.scope_type == "CLIENT":
            scope["clients"].append(entry.scope_id)
        if entry.scope_type == "SITE":
            scope["sites"].append(entry.scope_id)
        if entry.scope_type == "CONTRACT":
            scope["contracts"].append(entry.scope_id)
    return scope


def build_user_context(db: Session, user: models.User) -> dict[str, Any]:
    roles = get_user_roles(db, user)
    permissions = get_user_permissions(db, user)
    scope = get_user_scope(db, user)
    return {
        "roles": [role.nome for role in roles],
        "permissions": sorted(permissions),
        "scope": scope,
    }


def _is_hex(value: str) -> bool:
    if not value:
        return False
    return all(ch in "0123456789abcdef" for ch in value.lower())


def _verify_pbkdf2_hex(
    plain_password: str,
    salt_hex: str,
    hash_hex: str,
    iterations: int,
    digest: str = "sha512",
) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac(
        digest,
        plain_password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


def _verify_legacy_pbkdf2(plain_password: str, stored: str) -> bool:
    stripped = stored.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            salt_hex = payload.get("salt") or payload.get("saltHex")
            hash_hex = payload.get("passwordHash") or payload.get("hash")
            if salt_hex and hash_hex:
                return _verify_pbkdf2_hex(plain_password, salt_hex, hash_hex, 10000)
    if stored.startswith("pbkdf2$"):
        parts = stored.split("$")
        if len(parts) >= 5:
            digest = parts[1].lower()
            if digest not in {"sha512", "sha256"}:
                return False
            try:
                iterations = int(parts[2])
            except ValueError:
                iterations = 10000
            return _verify_pbkdf2_hex(plain_password, parts[3], parts[4], iterations, digest)
    for sep in (":", "$"):
        if sep in stored:
            salt_hex, hash_hex = stored.split(sep, 1)
            if _is_hex(salt_hex) and _is_hex(hash_hex) and len(hash_hex) >= 64 and len(hash_hex) % 2 == 0:
                return _verify_pbkdf2_hex(plain_password, salt_hex, hash_hex, 10000)
    return False


def verify_password_with_upgrade(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    if not hashed_password:
        return False, False
    if hashed_password.startswith("$2"):
        try:
            return pwd_context.verify(plain_password, hashed_password), False
        except Exception:
            return False, False
    if _verify_legacy_pbkdf2(plain_password, hashed_password):
        return True, True
    return False, False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    ok, _ = verify_password_with_upgrade(plain_password, hashed_password)
    return ok


def get_password_hash(password: str) -> str:
    if not isinstance(password, str):
        raise ValueError("Senha invalida para hash: envie somente a senha em texto do usuario.")
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError(
            "Senha maior que 72 bytes em UTF-8. Verifique se a variavel correta da senha foi enviada."
        )
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        tenant_id: str | None = payload.get("tenant_id")
        if user_id is None or tenant_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.tenant_id == tenant_id)
        .first()
    )
    if not user:
        raise credentials_exception
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inativo")
    return user


def get_current_user_from_token(token: str, db: Session) -> models.User:
    """
    Utilitário para validar token recebido fora do fluxo padrão (ex.: query param em rota de teste).
    Usa a mesma lógica de get_current_user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        tenant_id: str | None = payload.get("tenant_id")
        if user_id is None or tenant_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.tenant_id == tenant_id)
        .first()
    )
    if not user:
        raise credentials_exception
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inativo")
    return user


def get_current_platform_user(
    token: str = Depends(platform_oauth2_scheme), db: Session = Depends(get_db)
) -> models.PlatformUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        platform_user_id: str | None = payload.get("platform_user_id")
        role: str | None = payload.get("role")
        if platform_user_id is None or role is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.PlatformUser).filter(models.PlatformUser.id == platform_user_id).first()
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inativo")
    if user.role not in PLATFORM_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role nao permitido")
    return user


def require_platform_roles(*roles: str):
    def _dependency(
        user: models.PlatformUser = Depends(get_current_platform_user),
    ) -> models.PlatformUser:
        if roles and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao negada")
        return user

    return _dependency


def require_permission(permission_code: str):
    def _dependency(
        user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        permissions = get_user_permissions(db, user)
        if permission_code not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao negada")
        return user

    return _dependency


def require_permissions(*permission_codes: str):
    def _dependency(
        user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        permissions = get_user_permissions(db, user)
        missing = [code for code in permission_codes if code not in permissions]
        if missing:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao negada")
        return user

    return _dependency
