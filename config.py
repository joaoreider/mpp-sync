"""Carregamento e validação de variáveis de ambiente para o ETL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurações imutáveis lidas do arquivo .env."""

    odbc_connect: str | None
    odbc_dsn: str | None
    odbc_uid: str | None
    odbc_pwd: str | None
    local_mpp_dir: Path

    @property
    def database_url(self) -> str:
        """URL SQLAlchemy para conexão ODBC."""
        if self.odbc_connect:
            return build_odbc_database_url_from_connect(self.odbc_connect)
        if self.odbc_dsn is None:
            raise ValueError(
                "Configure ODBC_CONNECT ou ODBC_DSN no .env para conectar ao banco."
            )
        return build_odbc_database_url(self.odbc_dsn, self.odbc_uid, self.odbc_pwd)


def build_odbc_database_url_from_connect(odbc_connect: str) -> str:
    """Monta URL SQLAlchemy a partir de uma connection string ODBC completa."""
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_connect)}"


def build_odbc_database_url(
    dsn: str,
    uid: str | None = None,
    pwd: str | None = None,
) -> str:
    """Monta connection string SQLAlchemy (mssql+pyodbc) a partir de um DSN ODBC."""
    parts = [f"DSN={dsn}"]
    if uid:
        parts.append(f"UID={uid}")
    if pwd:
        parts.append(f"PWD={pwd}")
    return build_odbc_database_url_from_connect(";".join(parts))


def _get_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _resolve_local_mpp_dir() -> Path:
    """Resolve a pasta local que contém arquivos .mpp."""
    raw = os.getenv("LOCAL_MPP_DIR", "").strip()
    if not raw:
        raise ValueError("LOCAL_MPP_DIR é obrigatório")
    mpp_dir = Path(raw)
    if not mpp_dir.is_dir():
        raise ValueError(f"LOCAL_MPP_DIR não existe ou não é uma pasta: {mpp_dir}")
    return mpp_dir


def load_settings() -> Settings:
    """Carrega e valida todas as configurações necessárias para o pipeline."""
    odbc_connect = _get_env("ODBC_CONNECT")
    odbc_dsn = _get_env("ODBC_DSN")

    if not odbc_connect and not odbc_dsn:
        raise ValueError(
            "Variável de ambiente obrigatória ausente ou vazia: ODBC_CONNECT ou ODBC_DSN"
        )

    return Settings(
        odbc_connect=odbc_connect,
        odbc_dsn=odbc_dsn,
        odbc_uid=_get_env("ODBC_UID"),
        odbc_pwd=_get_env("ODBC_PWD"),
        local_mpp_dir=_resolve_local_mpp_dir(),
    )
