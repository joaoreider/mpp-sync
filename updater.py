"""Atualização do app a partir dos Releases do GitHub."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.8"
GITHUB_REPO = "joaoreider/mpp-sync"
ASSET_NAME = "MPPSync-Setup.exe"
USER_AGENT = f"MPPSync/{APP_VERSION}"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    tag: str
    version: str
    download_url: str
    html_url: str


def current_version() -> str:
    return APP_VERSION


def parse_version(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)


def is_newer(remote_version: str, local_version: str = APP_VERSION) -> bool:
    return parse_version(remote_version) > parse_version(local_version)


def fetch_latest_release() -> ReleaseInfo:
    """Consulta o último Release publicado no GitHub."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                "Nenhum Release encontrado no GitHub. Publique uma tag vX.Y.Z."
            ) from exc
        raise RuntimeError(f"Falha ao consultar GitHub ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Sem conexão para verificar atualização: {exc.reason}") from exc

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise RuntimeError("Release do GitHub sem tag_name.")

    download_url = None
    for asset in payload.get("assets") or []:
        if asset.get("name") == ASSET_NAME:
            download_url = asset.get("browser_download_url")
            break

    if not download_url:
        raise RuntimeError(
            f"Release {tag} não contém o asset {ASSET_NAME}."
        )

    return ReleaseInfo(
        tag=tag,
        version=tag.lstrip("vV"),
        download_url=str(download_url),
        html_url=str(payload.get("html_url") or ""),
    )


def download_installer(download_url: str, destination: Path | None = None) -> Path:
    """Baixa o instalador do Release para um arquivo temporário."""
    target = destination or Path(tempfile.gettempdir()) / ASSET_NAME
    request = urllib.request.Request(
        download_url,
        headers={"User-Agent": USER_AGENT},
    )
    logger.info("Baixando atualização de %s", download_url)
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
    return target


def resolve_app_exe() -> Path:
    """Caminho do executável atual (frozen) ou instalação padrão."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()

    for base in (
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        r"C:\Program Files",
    ):
        if not base:
            continue
        candidate = Path(base) / "MPPSync" / "MPPSync.exe"
        if candidate.exists():
            return candidate
    return Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "MPPSync" / "MPPSync.exe"


def launch_installer(installer_path: Path, app_exe: Path | None = None) -> Path:
    """Inicia o instalador elevado; retorna o caminho do log de update.

    Não encerra o app atual: o próprio instalador fecha o processo em execução
    e o script reabre o exe ao final. Assim, se o UAC for cancelado, o app
    continua aberto.
    """
    if os.name != "nt":
        raise RuntimeError("Atualização automática só está disponível no Windows.")

    import ctypes

    exe_path = app_exe or resolve_app_exe()
    log_path = Path(tempfile.gettempdir()) / "mppsync_update.log"
    bat_path = Path(tempfile.gettempdir()) / "mppsync_update.bat"

    bat_content = "\r\n".join(
        [
            "@echo off",
            "setlocal",
            f'set "LOG={log_path}"',
            'echo %DATE% %TIME% update_start> "%LOG%"',
            f'echo installer={installer_path}>> "%LOG%"',
            f'echo app={exe_path}>> "%LOG%"',
            f'"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS >> "%LOG%" 2>&1',
            "set ERR=%ERRORLEVEL%",
            'echo installer_exit=%ERR%>> "%LOG%"',
            "timeout /t 3 /nobreak >nul",
            f'if exist "{exe_path}" (',
            f'  start "" "{exe_path}"',
            '  echo restarted_primary>> "%LOG%"',
            ") else (",
            '  echo primary_missing>> "%LOG%"',
            '  if exist "%ProgramFiles%\\MPPSync\\MPPSync.exe" (',
            '    start "" "%ProgramFiles%\\MPPSync\\MPPSync.exe"',
            '    echo restarted_programfiles>> "%LOG%"',
            "  )",
            ")",
            'echo update_done>> "%LOG%"',
        ]
    ) + "\r\n"
    bat_path.write_text(bat_content, encoding="utf-8")

    # SW_SHOWNORMAL = 1 para o prompt UAC aparecer de forma previsível.
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(bat_path),
        None,
        str(bat_path.parent),
        1,
    )
    if result <= 32:
        raise RuntimeError(
            "Não foi possível iniciar o instalador (UAC cancelado ou falha). "
            "Baixe o Release e execute MPPSync-Setup.exe como administrador.\n"
            f"Log: {log_path}"
        )
    logger.info(
        "Instalador de atualização iniciado (ShellExecute=%s, app=%s, log=%s)",
        result,
        exe_path,
        log_path,
    )
    return log_path
