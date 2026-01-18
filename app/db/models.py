import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    slug = Column(String, nullable=True, unique=True)
    cnpj = Column(String, nullable=True)
    status = Column(String, nullable=False, default="ATIVO")
    tenant_type = Column(String, nullable=False, default="MSP")
    timezone = Column(String, nullable=False, default="America/Sao_Paulo")
    contato_email = Column(String, nullable=True)
    razao_social = Column(String, nullable=True)
    contato_nome = Column(String, nullable=True)
    contato_telefone = Column(String, nullable=True)
    segmento = Column(String, nullable=True)
    porte_empresa = Column(String, nullable=True)
    site_url = Column(String, nullable=True)
    billing_email = Column(String, nullable=True)
    billing_metodo = Column(String, nullable=True)
    billing_ciclo = Column(String, nullable=True)
    billing_dia_vencimento = Column(Integer, nullable=True)
    billing_proximo_vencimento = Column(Date, nullable=True)
    billing_observacoes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    contract_access = relationship("UserContractAccess", back_populates="tenant", cascade="all, delete-orphan")
    customer_accounts = relationship(
        "CustomerAccount", back_populates="tenant", cascade="all, delete-orphan"
    )
    sites = relationship("Site", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="tenant", cascade="all, delete-orphan")
    usage_meters = relationship("UsageMeter", back_populates="tenant", cascade="all, delete-orphan")
    overrides = relationship("TenantOverride", back_populates="tenant", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="tenant", cascade="all, delete-orphan")
    alerts = relationship("TenantAlert", back_populates="tenant", cascade="all, delete-orphan")
    contacts = relationship("TenantContact", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "login", name="uq_tenant_login"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    login = Column(String, nullable=False)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    client_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="users")
    contract_access = relationship("UserContractAccess", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    permissions = relationship("UserPermission", back_populates="user", cascade="all, delete-orphan")
    scopes = relationship("UserScope", back_populates="user", cascade="all, delete-orphan")


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (UniqueConstraint("email", name="uq_owner_email"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    uid = Column(String, nullable=True)
    email = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserContractAccess(Base):
    __tablename__ = "user_contract_access"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    contract_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="contract_access")
    user = relationship("User", back_populates="contract_access")


class Role(Base):
    __tablename__ = "roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    nome = Column(String, nullable=False)
    descricao = Column(String, nullable=True)
    is_system_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    users = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, nullable=False, unique=True)
    nome = Column(String, nullable=False)
    descricao = Column(String, nullable=True)

    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_overrides = relationship("UserPermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)
    permission_id = Column(String, ForeignKey("permissions.id"), nullable=False)

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")


class UserPermission(Base):
    __tablename__ = "user_permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    permission_id = Column(String, ForeignKey("permissions.id"), nullable=False)
    mode = Column(String, nullable=False, default="grant")

    user = relationship("User", back_populates="permissions")
    permission = relationship("Permission", back_populates="user_overrides")


class UserScope(Base):
    __tablename__ = "scopes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    scope_type = Column(String, nullable=False)
    scope_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="scopes")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    payload_resumo = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    client_code = Column(String, nullable=True)
    contract = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    document = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geocoded_at = Column(DateTime, nullable=True)
    geocode_status = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    status = Column(String, nullable=False, default="ATIVO")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="customer_accounts")
    sites = relationship("Site", back_populates="customer_account", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    customer_account_id = Column(String, ForeignKey("customer_accounts.id"), nullable=True)
    code = Column(String, nullable=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ATIVO")
    address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="sites")
    customer_account = relationship("CustomerAccount", back_populates="sites")


class Colaborador(Base):
    __tablename__ = "colaboradores"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    nome = Column(String, nullable=False)
    funcao = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ATIVO")
    coordenador_nome = Column(String, nullable=True)
    supervisor_nome = Column(String, nullable=True)
    contrato = Column(String, nullable=True)
    unidade = Column(String, nullable=True)
    especialidades = Column(JSON, nullable=True)
    observacoes = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SSMAOcorrencia(Base):
    __tablename__ = "ssma_ocorrencias"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    tipo = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ABERTA")
    gravidade = Column(String, nullable=False)
    contrato = Column(String, nullable=True)
    unidade = Column(String, nullable=True)
    descricao = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SSMAInspecao(Base):
    __tablename__ = "ssma_inspecoes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    contrato = Column(String, nullable=True)
    unidade = Column(String, nullable=True)
    resultado = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDENTE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SSMAAcao(Base):
    __tablename__ = "ssma_acoes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    responsavel = Column(String, nullable=True)
    prazo = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="PENDENTE")
    descricao = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Orcamento(Base):
    __tablename__ = "orcamentos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    cliente = Column(String, nullable=True)
    contrato = Column(String, nullable=True)
    unidade = Column(String, nullable=True)
    os_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="PENDENTE")
    total = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    itens = relationship("OrcamentoItem", back_populates="orcamento", cascade="all, delete-orphan")


class OrcamentoItem(Base):
    __tablename__ = "orcamento_itens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    orcamento_id = Column(String, ForeignKey("orcamentos.id"), nullable=False)
    descricao = Column(String, nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_unitario = Column(Integer, nullable=False, default=0)

    orcamento = relationship("Orcamento", back_populates="itens")


class SuprimentoRequisicao(Base):
    __tablename__ = "suprimentos_requisicoes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    os_id = Column(String, nullable=True)
    cliente = Column(String, nullable=True)
    contrato = Column(String, nullable=True)
    unidade = Column(String, nullable=True)
    solicitante = Column(String, nullable=True)
    status = Column(String, nullable=False, default="ABERTA")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    itens = relationship("SuprimentoItem", back_populates="requisicao", cascade="all, delete-orphan")


class SuprimentoItem(Base):
    __tablename__ = "suprimento_itens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    requisicao_id = Column(String, ForeignKey("suprimentos_requisicoes.id"), nullable=False)
    material = Column(String, nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    prioridade = Column(String, nullable=False, default="Media")
    observacao = Column(String, nullable=True)

    requisicao = relationship("SuprimentoRequisicao", back_populates="itens")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    code_human = Column(String, nullable=True)
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    contract_id = Column(String, nullable=True)
    site_id = Column(String, ForeignKey("sites.id"), nullable=True)
    requester_name = Column(String, nullable=True)
    requester_phone = Column(String, nullable=True)
    responsible_user_id = Column(String, nullable=True)
    asset_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    materials = Column(String, nullable=True)
    conclusion = Column(String, nullable=True)
    type = Column(String, nullable=True)
    status = Column(String, nullable=True, default="aberta")
    priority = Column(String, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    sla_due_at = Column(DateTime, nullable=True)
    sla_breached = Column(Boolean, nullable=True, default=False)
    assigned_user_id = Column(String, nullable=True)
    assigned_team_id = Column(String, nullable=True)
    completion_percent = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    checkin_data = Column(JSON, nullable=True)
    checkout_data = Column(JSON, nullable=True)
    totals = Column(JSON, nullable=True)
    signatures = Column(JSON, nullable=True)

    tenant = relationship("Tenant")
    client = relationship("Client")
    site = relationship("Site")
    items = relationship("WorkOrderItem", back_populates="work_order", cascade="all, delete-orphan")
    activities = relationship("WorkOrderActivity", back_populates="work_order", cascade="all, delete-orphan")
    events = relationship("WorkOrderEvent", back_populates="work_order", cascade="all, delete-orphan")


class WorkOrderItem(Base):
    __tablename__ = "work_order_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    work_order_id = Column(String, ForeignKey("work_orders.id"), nullable=False)
    question_text = Column(String, nullable=False)
    answer_type = Column(String, nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    answer_value = Column(String, nullable=True)
    answer_numeric = Column(Integer, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    work_order = relationship("WorkOrder", back_populates="items")
    attachments = relationship(
        "WorkOrderAttachment", back_populates="item", cascade="all, delete-orphan"
    )


class WorkOrderAttachment(Base):
    __tablename__ = "work_order_attachments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    work_order_id = Column(String, ForeignKey("work_orders.id"), nullable=False)
    item_id = Column(String, ForeignKey("work_order_items.id"), nullable=True)
    question_id = Column(String, nullable=True)
    scope = Column(String, nullable=False, default="QUESTION")
    file_name = Column(String, nullable=False)
    mime = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    url = Column(String, nullable=True)
    thumb_url = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    item = relationship("WorkOrderItem", back_populates="attachments")


class WorkOrderEvent(Base):
    __tablename__ = "work_order_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    work_order_id = Column(String, ForeignKey("work_orders.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    type = Column(String, nullable=False)
    client_timestamp = Column(DateTime, nullable=True)
    server_received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    lat = Column(String, nullable=True)
    lng = Column(String, nullable=True)
    accuracy_m = Column(Integer, nullable=True)
    altitude = Column(Integer, nullable=True)
    heading = Column(Integer, nullable=True)
    speed = Column(Integer, nullable=True)
    provider = Column(String, nullable=True)
    is_mock_location = Column(Boolean, nullable=True)
    device_id = Column(String, nullable=True)
    app_version = Column(String, nullable=True)
    offline_event_id = Column(String, nullable=True)
    sync_batch_id = Column(String, nullable=True)
    payload_resumo = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    work_order = relationship("WorkOrder", back_populates="events")


class WorkOrderActivity(Base):
    __tablename__ = "work_order_activities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    work_order_id = Column(String, ForeignKey("work_orders.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDENTE")
    started_at_client = Column(DateTime, nullable=True)
    ended_at_client = Column(DateTime, nullable=True)
    started_at_server = Column(DateTime, nullable=True)
    ended_at_server = Column(DateTime, nullable=True)
    duration_ms_client = Column(Integer, nullable=True)
    duration_ms_server = Column(Integer, nullable=True)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)

    work_order = relationship("WorkOrder", back_populates="activities")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("tenant_id", "tag", name="uq_asset_tag"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    site_id = Column(String, ForeignKey("sites.id"), nullable=True)
    tag = Column(String, nullable=False)
    name = Column(String, nullable=False)
    asset_type = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class OSType(Base):
    __tablename__ = "os_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "client_id", name="uq_os_type"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    __table_args__ = (UniqueConstraint("tenant_id", "title", "version", name="uq_questionnaire"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    title = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="ATIVO")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = relationship("QuestionnaireItem", back_populates="questionnaire", cascade="all, delete-orphan")


class QuestionnaireItem(Base):
    __tablename__ = "questionnaire_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    questionnaire_id = Column(String, ForeignKey("questionnaires.id"), nullable=False)
    question_text = Column(String, nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    answer_type = Column(String, nullable=False)
    items = Column(JSON, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    questionnaire = relationship("Questionnaire", back_populates="items")


class PublicLink(Base):
    __tablename__ = "public_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=True)
    allowed_view = Column(String, nullable=False, default="read_only")
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    audit_events = relationship("AuditEvent", back_populates="actor")
    overrides_created = relationship("TenantOverride", back_populates="created_by")
    impersonation_sessions = relationship("ImpersonationSession", back_populates="actor")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = Column(String, nullable=False, unique=True)
    descricao = Column(String, nullable=True)
    preco_mensal_centavos = Column(Integer, nullable=False, default=0)
    preco_anual_centavos = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    entitlements = relationship("PlanEntitlement", back_populates="plan", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="plan")


class PlanEntitlement(Base):
    __tablename__ = "plan_entitlements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id = Column(String, ForeignKey("plans.id"), nullable=False)
    key = Column(String, nullable=False)
    value_type = Column(String, nullable=False)
    value_bool = Column(Boolean, nullable=True)
    value_int = Column(Integer, nullable=True)
    value_string = Column(String, nullable=True)

    plan = relationship("Plan", back_populates="entitlements")


class TenantOverride(Base):
    __tablename__ = "tenant_overrides"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    key = Column(String, nullable=False)
    value_type = Column(String, nullable=False)
    value_bool = Column(Boolean, nullable=True)
    value_int = Column(Integer, nullable=True)
    value_string = Column(String, nullable=True)
    reason = Column(String, nullable=False)
    created_by_platform_user_id = Column(String, ForeignKey("platform_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="overrides")
    created_by = relationship("PlatformUser", back_populates="overrides_created")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(String, ForeignKey("plans.id"), nullable=False)
    status = Column(String, nullable=False, default="TRIAL")
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    invoices = relationship("Invoice", back_populates="subscription", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    subscription_id = Column(String, ForeignKey("subscriptions.id"), nullable=False)
    amount_centavos = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="PENDENTE")
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="invoices")
    subscription = relationship("Subscription", back_populates="invoices")


class UsageMeter(Base):
    __tablename__ = "usage_meters"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    users_count = Column(Integer, nullable=False, default=0)
    assets_count = Column(Integer, nullable=False, default=0)
    storage_mb = Column(Integer, nullable=False, default=0)
    ai_credits_used = Column(Integer, nullable=False, default=0)
    requests_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="usage_meters")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_platform_user_id = Column(String, ForeignKey("platform_users.id"), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    action = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="INFO")
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("PlatformUser", back_populates="audit_events")
    tenant = relationship("Tenant", back_populates="audit_events")


class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_platform_user_id = Column(String, ForeignKey("platform_users.id"), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    reason = Column(String, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE")

    actor = relationship("PlatformUser", back_populates="impersonation_sessions")
    tenant = relationship("Tenant")


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    code = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="BETA")
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    entitlement_map = relationship(
        "ProductEntitlementMap", back_populates="product", cascade="all, delete-orphan"
    )
    rollout_rule = relationship(
        "RolloutRule", back_populates="product", uselist=False, cascade="all, delete-orphan"
    )


class ProductEntitlementMap(Base):
    __tablename__ = "product_entitlement_map"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    entitlement_key = Column(String, nullable=False)
    rule_type = Column(String, nullable=False)
    value_bool = Column(Boolean, nullable=True)
    value_int = Column(Integer, nullable=True)
    value_string = Column(String, nullable=True)

    product = relationship("Product", back_populates="entitlement_map")


class RolloutRule(Base):
    __tablename__ = "rollout_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id"), nullable=False, unique=True)
    enabled_global = Column(Boolean, default=False, nullable=False)
    rollout_percent = Column(Integer, default=0, nullable=False)
    kill_switch = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="rollout_rule")


class TenantAlert(Base):
    __tablename__ = "tenant_alerts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(String, nullable=False)
    suggested_action = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="alerts")


class TenantContact(Base):
    __tablename__ = "tenant_contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False)
    telefone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="contacts")


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity", "file_hash", name="uq_import_dedup"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    entity = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False, default="upsert")
    status = Column(String, nullable=False, default="queued", index=True)
    file_url = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    file_hash = Column(String, nullable=False)
    template_version = Column(String, nullable=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    summary_json = Column(JSON, nullable=True)
    error_report_url = Column(String, nullable=True)
    preview_json = Column(JSON, nullable=True)
    logs_json = Column(JSON, nullable=True)


class ImportRowError(Base):
    __tablename__ = "import_row_errors"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    import_job_id = Column(String, ForeignKey("import_jobs.id"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    field = Column(String, nullable=True)
    message = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="error")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    entity = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    file_url = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_hash = Column(String, nullable=True)
    template_version = Column(String, nullable=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    summary_json = Column(JSON, nullable=True)


class CatalogArea(Base):
    __tablename__ = "catalog_area"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    equipment_types = relationship("CatalogEquipmentType", back_populates="area", cascade="all, delete-orphan")


class CatalogEquipmentType(Base):
    __tablename__ = "catalog_equipment_type"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    area_id = Column(String, ForeignKey("catalog_area.id"), nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    area = relationship("CatalogArea", back_populates="equipment_types")
    brands = relationship("CatalogBrand", back_populates="equipment_type", cascade="all, delete-orphan")


class CatalogBrand(Base):
    __tablename__ = "catalog_brand"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    equipment_type_id = Column(String, ForeignKey("catalog_equipment_type.id"), nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    equipment_type = relationship("CatalogEquipmentType", back_populates="brands")


class ProblemSession(Base):
    __tablename__ = "problem_session"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_name_snapshot = Column(String, nullable=False)
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    client_name_snapshot = Column(String, nullable=True)
    client_other_text = Column(String, nullable=True)
    status = Column(String, nullable=False, default="draft")
    area_id = Column(String, ForeignKey("catalog_area.id"), nullable=False)
    equipment_type_id = Column(String, ForeignKey("catalog_equipment_type.id"), nullable=False)
    brand_id = Column(String, ForeignKey("catalog_brand.id"), nullable=False)
    other_equipment_text = Column(String, nullable=True)
    other_brand_text = Column(String, nullable=True)
    model_text = Column(String, nullable=True)
    model_unknown = Column(Boolean, default=False, nullable=False)
    error_code_text = Column(String, nullable=True)
    error_code_unknown = Column(Boolean, default=False, nullable=False)
    short_problem_text = Column(String(200), nullable=False)
    attachments_count = Column(Integer, default=0, nullable=False)
    ai_quick_result_json = Column(JSON, nullable=True)
    ai_advanced_result_json = Column(JSON, nullable=True)
    ai_model_used = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    test_inputs = relationship("ProblemTestInput", back_populates="session", cascade="all, delete-orphan")
    attachments = relationship("ProblemAttachment", back_populates="session", cascade="all, delete-orphan")
    public_links = relationship("ProblemPublicLink", back_populates="session", cascade="all, delete-orphan")


class ProblemTestInput(Base):
    __tablename__ = "problem_test_input"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("problem_session.id"), nullable=False)
    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    value = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ProblemSession", back_populates="test_inputs")


class ProblemAttachment(Base):
    __tablename__ = "problem_attachment"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("problem_session.id"), nullable=False)
    kind = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String, nullable=True)

    session = relationship("ProblemSession", back_populates="attachments")


class ProblemPublicLink(Base):
    __tablename__ = "problem_public_link"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("problem_session.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ProblemSession", back_populates="public_links")


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tipo_equipamento = Column(String, nullable=False)
    marca = Column(String, nullable=False)
    modelo = Column(String, nullable=False)
    problema_texto = Column(String, nullable=False)
    problema_tags = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="processing")
    openai_model = Column(String, nullable=True)
    confidence_overall = Column(Float, nullable=True)
    error_message = Column(String, nullable=True)
    os_id = Column(String, nullable=True)
    asset_id = Column(String, nullable=True)

    images = relationship("ScanImage", back_populates="scan", cascade="all, delete-orphan")
    signals = relationship("ScanSignal", back_populates="scan", cascade="all, delete-orphan")
    results = relationship("ScanResult", back_populates="scan", cascade="all, delete-orphan")


class ScanImage(Base):
    __tablename__ = "scan_images"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String, ForeignKey("scan_sessions.id"), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    storage_url = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scan = relationship("ScanSession", back_populates="images")


class ScanSignal(Base):
    __tablename__ = "scan_signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String, ForeignKey("scan_sessions.id"), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    signals_json = Column(JSON, nullable=False)
    extraction_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scan = relationship("ScanSession", back_populates="signals")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String, ForeignKey("scan_sessions.id"), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    result_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scan = relationship("ScanSession", back_populates="results")
