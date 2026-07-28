"""Carregamento e validação de variáveis de ambiente para o ETL."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

APP_NAME = "MPPSync"


def _app_dir() -> Path:
    """Pasta base do app: junto ao .exe quando empacotado, senão a do código."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _program_data_dir() -> Path:
    """Pasta gravável compartilhada por instalações Windows."""
    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / APP_NAME
    return _app_dir()


def app_data_dir() -> Path:
    """Pasta gravável para config e logs do app."""
    data_dir = _program_data_dir() if getattr(sys, "frozen", False) else _app_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _env_candidates() -> tuple[Path, ...]:
    app_env = _app_dir() / ".env"
    if getattr(sys, "frozen", False):
        return (_program_data_dir() / ".env", app_env)
    return (app_env,)


def _env_path() -> Path:
    """Resolve o .env ativo, priorizando ProgramData quando empacotado."""
    candidates = _env_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


_ENV_PATH = _env_path()
load_dotenv(_ENV_PATH)

CONFIG_KEYS = (
    "ODBC_CONNECT",
    "ODBC_DSN",
    "ODBC_UID",
    "ODBC_PWD",
    "LOCAL_MPP_DIR",
)


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


def load_config_values() -> dict[str, str]:
    """Carrega valores atuais para preencher a interface sem validar obrigatórios."""
    load_dotenv(_env_path(), override=True)
    return {key: os.getenv(key, "") for key in CONFIG_KEYS}


def save_config_values(values: dict[str, str], env_path: Path | None = None) -> None:
    """Atualiza chaves conhecidas no .env preservando outras linhas existentes."""
    active_env_path = env_path or _env_path()
    normalized_values = {
        key: values.get(key, "").strip()
        for key in CONFIG_KEYS
        if key in values
    }
    existing_lines = (
        active_env_path.read_text(encoding="utf-8").splitlines()
        if active_env_path.exists()
        else []
    )
    seen_keys: set[str] = set()
    updated_lines: list[str] = []

    for line in existing_lines:
        key = _parse_env_key(line)
        if key in normalized_values:
            updated_lines.append(_format_env_line(key, normalized_values[key]))
            seen_keys.add(key)
        else:
            updated_lines.append(line)

    for key in CONFIG_KEYS:
        if key in normalized_values and key not in seen_keys:
            updated_lines.append(_format_env_line(key, normalized_values[key]))

    active_env_path.parent.mkdir(parents=True, exist_ok=True)
    active_env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    load_dotenv(active_env_path, override=True)


def _parse_env_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _value = stripped.split("=", 1)
    key = key.strip()
    return key if key in CONFIG_KEYS else None


def _format_env_line(key: str, value: str) -> str:
    return f"{key}={_quote_env_value(value)}"


def _quote_env_value(value: str) -> str:
    if not value:
        return ""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _resolve_local_mpp_dir() -> Path:
    """Resolve a pasta local que contém arquivos .mpp."""
    raw = os.getenv("LOCAL_MPP_DIR", "").strip()
    if not raw:
        raise ValueError("LOCAL_MPP_DIR é obrigatório")
    mpp_dir = Path(raw)
    mpp_dir.mkdir(parents=True, exist_ok=True)
    if not mpp_dir.is_dir():
        raise ValueError(f"LOCAL_MPP_DIR não existe ou não é uma pasta: {mpp_dir}")
    return mpp_dir


def load_settings() -> Settings:
    """Carrega e valida todas as configurações necessárias para o pipeline."""
    load_dotenv(_env_path(), override=True)
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
