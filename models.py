"""Modelos SQLAlchemy para projetos e tarefas do MS Project."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Engine,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

_engine_cache: dict[str, Engine] = {}


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy."""


class Projeto(Base):
    """Representa um projeto importado do MS Project."""

    __tablename__ = "mpp_sync_projetos"
    __table_args__ = (UniqueConstraint("nome_projeto", name="uq_mpp_sync_projetos_nome_projeto"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome_projeto: Mapped[str] = mapped_column(String(500), nullable=False)
    gerente: Mapped[str | None] = mapped_column(String(255))
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    percentual_concluido: Mapped[float | None] = mapped_column(Numeric(5, 2))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tarefas: Mapped[list[Tarefa]] = relationship(
        "Tarefa",
        back_populates="projeto",
        cascade="all, delete-orphan",
    )


class Tarefa(Base):
    """Representa uma tarefa vinculada a um projeto."""

    __tablename__ = "mpp_sync_tarefas"
    __table_args__ = (
        UniqueConstraint(
            "id_projeto",
            "id_tarefa_project",
            name="uq_mpp_sync_tarefas_projeto_id_tarefa_project",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_projeto: Mapped[int] = mapped_column(
        ForeignKey("mpp_sync_projetos.id", ondelete="CASCADE"),
        nullable=False,
    )
    nome_tarefa: Mapped[str] = mapped_column(String(500), nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    inicio_do_plano_base: Mapped[date | None] = mapped_column(Date)
    conclusao_do_plano_base: Mapped[date | None] = mapped_column(Date)
    percentual_concluido: Mapped[float | None] = mapped_column(Numeric(5, 2))
    duracao: Mapped[float | None] = mapped_column(Numeric(18, 2))
    custo: Mapped[float | None] = mapped_column(Numeric(18, 2))
    trabalho: Mapped[float | None] = mapped_column(Numeric(18, 2))
    id_tarefa_project: Mapped[int] = mapped_column(nullable=False)

    projeto: Mapped[Projeto] = relationship("Projeto", back_populates="tarefas")


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


def _ensure_tarefa_columns(engine) -> None:
    """Adiciona colunas novas em bancos já existentes."""
    inspector = inspect(engine)
    if "mpp_sync_tarefas" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("mpp_sync_tarefas")}
    new_columns = {
        "inicio_do_plano_base": "DATE",
        "conclusao_do_plano_base": "DATE",
        "duracao": "DECIMAL(18, 2)",
    }

    with engine.begin() as connection:
        for column_name, column_type in new_columns.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE mpp_sync_tarefas ADD {column_name} {column_type}")
                )


def init_db(database_url: str) -> None:
    """Cria apenas as tabelas deste projeto caso ainda não existam."""
    engine = get_engine(database_url)
    Base.metadata.create_all(
        engine,
        tables=[Projeto.__table__, Tarefa.__table__],
    )
    _ensure_tarefa_columns(engine)
