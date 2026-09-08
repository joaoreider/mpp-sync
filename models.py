"""Modelos SQLAlchemy alinhados às 3 tabelas do Power BI / Project Online."""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Engine,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

_engine_cache: dict[str, Engine] = {}

_DROP_ORDER = (
    "linhas_base_faseadas_tarefa",
    "conjunto_dados_faseados_tarefa",
    "tarefas",
    "projetos",
)


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy."""


class Tarefa(Base):
    """Equivalente ao dataset Tarefas do Project Online / Power BI."""

    __tablename__ = "tarefas"
    __table_args__ = (
        UniqueConstraint(
            "nome_do_projeto",
            "id_tarefa",
            name="uq_tarefas_projeto_id_tarefa",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome_do_projeto: Mapped[str] = mapped_column(String(500), nullable=False)
    id_tarefa: Mapped[int] = mapped_column(nullable=False)
    nome_tarefa: Mapped[str] = mapped_column(String(500), nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_conclusao: Mapped[date | None] = mapped_column(Date)
    desvio_da_conclusao: Mapped[float | None] = mapped_column(Numeric(18, 2))
    duracao_da_tarefa: Mapped[float | None] = mapped_column(Numeric(18, 2))
    duracao_real_da_tarefa: Mapped[float | None] = mapped_column(Numeric(18, 2))
    ordem: Mapped[int | None] = mapped_column()
    spi_da_tarefa: Mapped[float | None] = mapped_column(Numeric(18, 6))
    id_obra: Mapped[str | None] = mapped_column(String(255))
    tarefa_e_resumo: Mapped[bool | None] = mapped_column(Boolean)
    tarefa_esta_ativa: Mapped[bool | None] = mapped_column(Boolean)
    wbs_da_tarefa: Mapped[str | None] = mapped_column(String(255))


class ConjuntoDadosFaseadosTarefa(Base):
    """Equivalente a ConjuntoDeDadosFaseadosNoTempoDaTarefa."""

    __tablename__ = "conjunto_dados_faseados_tarefa"
    __table_args__ = (
        UniqueConstraint(
            "nome_do_projeto",
            "id_tarefa",
            "hora_por_dia",
            name="uq_conjunto_dados_faseados_tarefa_chave",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome_do_projeto: Mapped[str] = mapped_column(String(500), nullable=False)
    id_tarefa: Mapped[int] = mapped_column(nullable=False)
    hora_por_dia: Mapped[date] = mapped_column(Date, nullable=False)
    custo_tarefa: Mapped[float | None] = mapped_column(Numeric(18, 2))
    custo_real_da_tarefa: Mapped[float | None] = mapped_column(Numeric(18, 2))


class LinhaBaseFaseadaTarefa(Base):
    """Equivalente a LinhaDeBaseDoConjuntoDeDadosFaseadosNoTempoDaTarefa."""

    __tablename__ = "linhas_base_faseadas_tarefa"
    __table_args__ = (
        UniqueConstraint(
            "nome_do_projeto",
            "id_tarefa",
            "hora_por_dia",
            "numero_linha_base",
            name="uq_linhas_base_faseadas_tarefa_chave",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome_do_projeto: Mapped[str] = mapped_column(String(500), nullable=False)
    id_tarefa: Mapped[int] = mapped_column(nullable=False)
    hora_por_dia: Mapped[date] = mapped_column(Date, nullable=False)
    numero_linha_base: Mapped[int] = mapped_column(nullable=False)
    custo_de_linha_base: Mapped[float | None] = mapped_column(Numeric(18, 2))


def get_engine(database_url: str) -> Engine:
    """Cria (ou reutiliza) engine SQLAlchemy a partir da connection string."""
    if database_url not in _engine_cache:
        # use_setinputsizes=False evita HY104 (Invalid precision value)
        # com o driver legado "SQL Server" e CAST(? AS NVARCHAR(max)).
        _engine_cache[database_url] = create_engine(
            database_url,
            future=True,
            fast_executemany=True,
            use_setinputsizes=False,
        )
    return _engine_cache[database_url]


def get_session_factory(database_url: str):
    """Retorna factory de sessões vinculada ao engine configurado."""
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _needs_schema_reset(engine: Engine) -> bool:
    """Detecta schema legado (projetos ou tarefas sem nome_do_projeto)."""
    inspector = inspect(engine)
    tables = {name.lower() for name in inspector.get_table_names()}
    if "projetos" in tables:
        return True
    if "tarefas" in tables:
        columns = {
            column["name"].lower()
            for column in inspector.get_columns("tarefas")
        }
        if "nome_do_projeto" not in columns or "id_projeto" in columns:
            return True
    if "linhas_base_faseadas_tarefa" in tables:
        columns = {
            column["name"].lower()
            for column in inspector.get_columns("linhas_base_faseadas_tarefa")
        }
        if "nome_do_projeto" not in columns or "custo_de_linha_base" not in columns:
            return True
    return False


def _drop_app_tables(engine: Engine) -> None:
    """Remove tabelas do app na ordem segura (filhas antes de pais)."""
    inspector = inspect(engine)
    existing = {name.lower() for name in inspector.get_table_names()}
    with engine.begin() as connection:
        for table_name in _DROP_ORDER:
            if table_name.lower() in existing:
                connection.execute(text(f"DROP TABLE {table_name}"))


def init_db(database_url: str) -> None:
    """Garante as 3 tabelas Power BI; reseta se o schema legado ainda existir."""
    engine = get_engine(database_url)
    if _needs_schema_reset(engine):
        _drop_app_tables(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            Tarefa.__table__,
            ConjuntoDadosFaseadosTarefa.__table__,
            LinhaBaseFaseadaTarefa.__table__,
        ],
    )
