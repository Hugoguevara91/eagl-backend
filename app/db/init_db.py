import os

admin_password = "admin123"
admin_login = "Admin"
admin_email = "admin@eagl.com.br"
platform_owner_email = "platform.owner@eagl.com.br"
platform_owner_password = "admin123"
RESET_DEFAULT_PASSWORDS = os.getenv("RESET_DEFAULT_PASSWORDS", "").strip().lower() in {"1", "true", "yes"}

from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db import models
from app.db.session import SessionLocal


def _slugify(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace("--", "-")
    )


def _ensure_missing_columns(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    existing_tables = set(inspector.get_table_names())
    for table_name, table in models.Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"ALTER TABLE {preparer.quote(table_name)} "
                        f"ADD COLUMN {preparer.quote(column.name)} {col_type}"
                    )
                )


def ensure_platform_schema(engine) -> None:
    inspector = inspect(engine)
    if "tenants" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("tenants")}
        updates: list[str] = []
        with engine.begin() as connection:
            if "slug" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN slug VARCHAR"))
            if "cnpj" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN cnpj VARCHAR"))
            if "timezone" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN timezone VARCHAR"))
                updates.append("UPDATE tenants SET timezone = 'America/Sao_Paulo' WHERE timezone IS NULL")
            if "tenant_type" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN tenant_type VARCHAR"))
                updates.append("UPDATE tenants SET tenant_type = 'MSP' WHERE tenant_type IS NULL")
            if "contato_email" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN contato_email VARCHAR"))
            if "razao_social" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN razao_social VARCHAR"))
            if "contato_nome" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN contato_nome VARCHAR"))
            if "contato_telefone" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN contato_telefone VARCHAR"))
            if "segmento" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN segmento VARCHAR"))
            if "porte_empresa" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN porte_empresa VARCHAR"))
            if "site_url" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN site_url VARCHAR"))
            if "billing_email" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_email VARCHAR"))
                updates.append(
                    "UPDATE tenants SET billing_email = contato_email "
                    "WHERE billing_email IS NULL AND contato_email IS NOT NULL"
                )
            if "billing_metodo" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_metodo VARCHAR"))
            if "billing_ciclo" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_ciclo VARCHAR"))
            if "billing_dia_vencimento" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_dia_vencimento INTEGER"))
            if "billing_proximo_vencimento" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_proximo_vencimento DATE"))
            if "billing_observacoes" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN billing_observacoes VARCHAR"))
            if "updated_at" not in columns:
                connection.execute(text("ALTER TABLE tenants ADD COLUMN updated_at TIMESTAMP"))
                updates.append("UPDATE tenants SET updated_at = created_at WHERE updated_at IS NULL")
            if "tenant_type" in columns:
                updates.append("UPDATE tenants SET tenant_type = 'MSP' WHERE tenant_type IS NULL")
            for statement in updates:
                connection.execute(text(statement))
    if "tenant_contacts" not in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE tenant_contacts (
                        id VARCHAR PRIMARY KEY,
                        tenant_id VARCHAR NOT NULL REFERENCES tenants(id),
                        nome VARCHAR NOT NULL,
                        email VARCHAR NOT NULL,
                        telefone VARCHAR NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
    if "owners" not in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE owners (
                        id VARCHAR PRIMARY KEY,
                        uid VARCHAR NULL,
                        email VARCHAR NOT NULL,
                        status VARCHAR NOT NULL DEFAULT 'ACTIVE',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_owner_email ON owners (email)"))
    _ensure_missing_columns(engine)


def ensure_rbac_defaults(db: Session) -> None:
    permissions_catalog = [
        ("os.view", "Visualizar OS", "Permite listar e visualizar ordens de servico"),
        ("os.edit", "Editar OS", "Permite editar ordens de servico"),
        ("os.close", "Fechar OS", "Permite finalizar ordens de servico"),
        ("os.close.critical", "Fechar OS critica", "Permite fechar OS com prioridade critica"),
        ("os.checkin", "Check-in OS", "Permite registrar check-in"),
        ("os.checkout", "Check-out OS", "Permite registrar check-out"),
        ("os.activity", "Atividades OS", "Permite iniciar/pausar/finalizar atividades"),
        ("os.share", "Compartilhar OS", "Permite gerar link publico de OS"),
        ("collaborators.view", "Visualizar colaboradores", "Permite listar colaboradores"),
        ("collaborators.manage", "Gerenciar colaboradores", "Permite criar e editar colaboradores"),
        ("ssma.view", "Visualizar SSMA", "Permite acessar SSMA"),
        ("ssma.manage", "Gerenciar SSMA", "Permite criar e editar SSMA"),
        ("budgets.view", "Visualizar orcamentos", "Permite acessar orcamentos"),
        ("budgets.manage", "Gerenciar orcamentos", "Permite criar e editar orcamentos"),
        ("supplies.view", "Visualizar suprimentos", "Permite acessar suprimentos"),
        ("supplies.manage", "Gerenciar suprimentos", "Permite criar e editar suprimentos"),
        ("clients.view", "Visualizar clientes", "Permite listar clientes"),
        ("clients.manage", "Gerenciar clientes", "Permite criar e editar clientes"),
        ("assets.view", "Visualizar ativos", "Permite listar ativos"),
        ("assets.manage", "Gerenciar ativos", "Permite criar e editar ativos"),
        ("users.manage", "Gerenciar usuarios", "Permite criar e editar usuarios"),
        ("roles.manage", "Gerenciar papeis", "Permite criar e editar papeis"),
        ("permissions.view", "Visualizar permissoes", "Permite consultar catalogo de permissoes"),
        ("audit.view", "Visualizar auditoria", "Permite acessar logs de auditoria"),
        ("reports.view", "Visualizar relatorios", "Permite acessar relatorios"),
        ("settings.manage", "Gerenciar configuracoes", "Permite alterar configuracoes do tenant"),
        ("cadastros.importar", "Importar cadastros", "Permite importar dados em massa"),
        ("cadastros.exportar", "Exportar cadastros", "Permite exportar dados em massa"),
        ("auditoria.visualizar_importacoes", "Visualizar importacoes", "Permite acessar historico de importacoes"),
    ]

    existing_permissions = {p.code: p for p in db.query(models.Permission).all()}
    for code, nome, descricao in permissions_catalog:
        if code not in existing_permissions:
            db.add(models.Permission(code=code, nome=nome, descricao=descricao))
    db.commit()

    role_templates = [
        ("TENANT_ADMIN", "Administrador", True),
        ("GERENTE", "Gerente", True),
        ("COORDENADOR", "Coordenador", True),
        ("LIDER_CONTRATO", "Lider de Contrato", True),
        ("SUPERVISOR", "Supervisor", True),
        ("TECNICO", "Tecnico", True),
        ("PLANEJAMENTO", "Planejamento", True),
        ("ORCAMENTISTA", "Orcamentista", True),
        ("SUPRIMENTOS", "Suprimentos", True),
        ("SSMA", "SSMA", True),
        ("CLIENTE", "Cliente", True),
    ]

    permission_by_code = {p.code: p for p in db.query(models.Permission).all()}
    all_permissions = list(permission_by_code.values())
    role_permissions_map = {
        "TENANT_ADMIN": list(permission_by_code.keys()),
        "GERENTE": [
            "os.view",
            "os.edit",
            "os.close",
            "os.share",
            "collaborators.view",
            "collaborators.manage",
            "ssma.view",
            "ssma.manage",
            "budgets.view",
            "budgets.manage",
            "supplies.view",
            "supplies.manage",
            "clients.view",
            "assets.view",
            "reports.view",
            "audit.view",
            "cadastros.importar",
            "cadastros.exportar",
            "auditoria.visualizar_importacoes",
        ],
        "COORDENADOR": [
            "os.view",
            "os.edit",
            "os.close",
            "os.share",
            "collaborators.view",
            "ssma.view",
            "budgets.view",
            "supplies.view",
            "clients.view",
            "assets.view",
            "reports.view",
            "cadastros.importar",
            "cadastros.exportar",
            "auditoria.visualizar_importacoes",
        ],
        "SUPERVISOR": [
            "os.view",
            "os.edit",
            "os.close",
            "ssma.view",
            "clients.view",
            "assets.view",
        ],
        "LIDER_CONTRATO": [
            "os.view",
            "os.edit",
            "ssma.view",
            "budgets.view",
            "supplies.view",
        ],
        "TECNICO": ["os.view", "os.edit", "os.checkin", "os.checkout", "os.activity", "ssma.view", "ssma.manage"],
        "PLANEJAMENTO": ["os.view", "assets.view", "reports.view"],
        "ORCAMENTISTA": ["os.view", "reports.view", "budgets.view", "budgets.manage"],
        "SUPRIMENTOS": ["os.view", "supplies.view", "supplies.manage"],
        "SSMA": ["ssma.view", "ssma.manage"],
        "CLIENTE": ["os.view", "reports.view"],
    }

    tenants = db.query(models.Tenant).all()
    for tenant in tenants:
        existing_roles = {
            role.nome: role for role in db.query(models.Role).filter(models.Role.tenant_id == tenant.id).all()
        }
        for code, descricao, is_default in role_templates:
            if code not in existing_roles:
                role = models.Role(
                    tenant_id=tenant.id,
                    nome=code,
                    descricao=descricao,
                    is_system_default=is_default,
                )
                db.add(role)
                db.flush()
                perms = role_permissions_map.get(code, [])
                for perm_code in perms:
                    permission = permission_by_code.get(perm_code)
                    if permission:
                        db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
        db.commit()

    # Garantir que todas as roles tenham todas as permissoes.
    roles = db.query(models.Role).all()
    for role in roles:
        for permission in all_permissions:
            exists = (
                db.query(models.RolePermission)
                .filter(
                    models.RolePermission.role_id == role.id,
                    models.RolePermission.permission_id == permission.id,
                )
                .first()
            )
            if not exists:
                db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()

    users = db.query(models.User).all()
    for user in users:
        tenant_roles = (
            db.query(models.Role).filter(models.Role.tenant_id == user.tenant_id).all()
        )
        role_by_name = {role.nome: role for role in tenant_roles}
        target_role = role_by_name.get(user.role) or role_by_name.get("TENANT_ADMIN")
        if target_role:
            has_role = (
                db.query(models.UserRole)
                .filter(models.UserRole.user_id == user.id, models.UserRole.role_id == target_role.id)
                .first()
            )
            if not has_role:
                db.add(models.UserRole(user_id=user.id, role_id=target_role.id))
    db.commit()


def seed_initial_data() -> None:
    db: Session = SessionLocal()
    try:
        tenant = db.query(models.Tenant).first()
        if not tenant:
            tenant = models.Tenant(
                name="Best Clima",
                slug=_slugify("best-clima"),
                status="ATIVO",
                tenant_type="MSP",
                timezone="America/Sao_Paulo",
                contato_email=admin_email,
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        elif not tenant.slug:
            tenant.slug = _slugify(tenant.name)
        if not tenant.tenant_type:
            tenant.tenant_type = "MSP"

        admin_user = (
            db.query(models.User)
            .filter(
                models.User.tenant_id == tenant.id,
                or_(
                    models.User.login == admin_login,
                    models.User.login == admin_login.lower(),
                    models.User.email == admin_email,
                ),
            )
            .first()
        )
        if not admin_user:
            admin_user = models.User(
                tenant_id=tenant.id,
                name="Administrador",
                login=admin_login,
                email=admin_email,
                password_hash=get_password_hash(admin_password),
                role="TENANT_ADMIN",
                status="active",
                client_id=None,
            )
            db.add(admin_user)
        else:
            admin_user.name = "Administrador"
            admin_user.login = admin_login
            admin_user.email = admin_email
            admin_user.role = "TENANT_ADMIN"
            admin_user.status = "active"
            if RESET_DEFAULT_PASSWORDS or not admin_user.password_hash:
                admin_user.password_hash = get_password_hash(admin_password)
        db.commit()
        db.refresh(admin_user)
        platform_owner = (
            db.query(models.PlatformUser)
            .filter(models.PlatformUser.email == platform_owner_email)
            .first()
        )
        if not platform_owner:
            platform_owner = models.PlatformUser(
                nome="Platform Owner",
                email=platform_owner_email,
                password_hash=get_password_hash(platform_owner_password),
                role="PLATFORM_OWNER",
                is_active=True,
                mfa_enabled=False,
            )
            db.add(platform_owner)
        else:
            platform_owner.nome = "Platform Owner"
            platform_owner.role = "PLATFORM_OWNER"
            platform_owner.is_active = True
            if RESET_DEFAULT_PASSWORDS or not platform_owner.password_hash:
                platform_owner.password_hash = get_password_hash(platform_owner_password)
        db.commit()
        db.refresh(platform_owner)
        _seed_solver_catalog(db)
        print("Seed OK: Admin/admin123 | Platform Owner/admin123")
    finally:
        db.close()


def _seed_solver_catalog(db: Session) -> None:
    areas = [
        ("HVAC", "HVAC"),
        ("ELETRICA", "Elétrica"),
        ("AUTOMACAO", "Automação"),
        ("UTILIDADES", "Utilidades"),
    ]
    area_by_code = {
        area.code: area
        for area in db.query(models.CatalogArea)
        .filter(models.CatalogArea.tenant_id.is_(None))
        .all()
    }
    for code, name in areas:
        if code not in area_by_code:
            area = models.CatalogArea(code=code, name=name, is_active=True, tenant_id=None)
            db.add(area)
            db.flush()
            area_by_code[code] = area

    hvac_types = [
        ("SPLIT", "Split"),
        ("VRF", "VRF / VRV"),
        ("CHILLER", "Chiller"),
        ("FANCOIL", "Fancoil"),
        ("SELF_CONTAINED", "Self Contained"),
        ("UNIDADE_CONDENSADORA", "Unidade Condensadora"),
        ("UNIDADE_EVAPORADORA", "Unidade Evaporadora"),
        ("VENTILADOR", "Ventilador"),
        ("EXAUSTOR", "Exaustor"),
        ("CORTINA_AR", "Cortina de Ar"),
        ("TORRE_RESFRIAMENTO", "Torre de Resfriamento"),
        ("AQUECEDOR", "Aquecedor"),
        ("OTHER", "Outro"),
    ]
    other_types = [("OTHER", "Outro")]

    def ensure_type(area_code: str, items: list[tuple[str, str]]):
        area = area_by_code.get(area_code)
        if not area:
            return {}
        existing = {
            item.code: item
            for item in db.query(models.CatalogEquipmentType)
            .filter(
                models.CatalogEquipmentType.area_id == area.id,
                models.CatalogEquipmentType.tenant_id.is_(None),
            )
            .all()
        }
        for code, name in items:
            if code not in existing:
                obj = models.CatalogEquipmentType(
                    area_id=area.id,
                    code=code,
                    name=name,
                    is_active=True,
                    tenant_id=None,
                )
                db.add(obj)
                db.flush()
                existing[code] = obj
        return existing

    hvac_type_map = ensure_type("HVAC", hvac_types)
    eletrica_type_map = ensure_type("ELETRICA", other_types)
    automacao_type_map = ensure_type("AUTOMACAO", other_types)
    utilidades_type_map = ensure_type("UTILIDADES", other_types)

    hvac_brands = [
        ("LG", "LG"),
        ("DAIKIN", "Daikin"),
        ("CARRIER", "Carrier"),
        ("TRANE", "Trane"),
        ("SAMSUNG", "Samsung"),
        ("HITACHI", "Hitachi"),
        ("YORK", "York"),
        ("MIDEA", "Midea"),
        ("FUJITSU", "Fujitsu"),
        ("SPRINGER", "Springer"),
        ("RHEEM", "Rheem"),
        ("OTHER", "Outro"),
    ]
    general_brands = [
        ("WEG", "WEG"),
        ("SIEMENS", "Siemens"),
        ("SCHNEIDER", "Schneider Electric"),
        ("ABB", "ABB"),
        ("DANFOSS", "Danfoss"),
        ("EATON", "Eaton"),
        ("ROCKWELL", "Rockwell"),
        ("OTHER", "Outro"),
    ]

    def ensure_brands(type_map: dict, brands: list[tuple[str, str]]):
        for type_obj in type_map.values():
            existing = {
                item.code: item
                for item in db.query(models.CatalogBrand)
                .filter(
                    models.CatalogBrand.equipment_type_id == type_obj.id,
                    models.CatalogBrand.tenant_id.is_(None),
                )
                .all()
            }
            for code, name in brands:
                if code not in existing:
                    db.add(
                        models.CatalogBrand(
                            equipment_type_id=type_obj.id,
                            code=code,
                            name=name,
                            is_active=True,
                            tenant_id=None,
                        )
                    )

    ensure_brands(hvac_type_map, hvac_brands)
    ensure_brands(eletrica_type_map, general_brands)
    ensure_brands(automacao_type_map, general_brands)
    ensure_brands(utilidades_type_map, general_brands)
    db.commit()
