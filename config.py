"""Carregamento e validação de variáveis de ambiente para o ETL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurações imutáveis lidas do arquivo .env."""

    database_url: str
    local_mpp_dir: Path


def _get_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _require_env(*names: str) -> str:
    value = _get_env(*names)
    display_name = " ou ".join(names)
    if value is None:
        raise ValueError(
            f"Variável de ambiente obrigatória ausente ou vazia: {display_name}"
        )
    return value


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
    return Settings(
        database_url=_require_env("DATABASE_URL"),
        local_mpp_dir=_resolve_local_mpp_dir(),
    )
