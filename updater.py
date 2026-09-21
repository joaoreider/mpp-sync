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

APP_VERSION = "1.0.18"
GITHUB_REPO = "joaoreider/mpp-sync"
ASSET_NAME = "MPPSync-Setup.exe"
APP_EXE_NAME = "MPPSync.exe"
INNO_LOG_NAME = "mppsync_inno.log"
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


def _release_asset_url(payload: dict) -> str | None:
    for asset in payload.get("assets") or []:
        if asset.get("name") == ASSET_NAME:
            url = asset.get("browser_download_url")
            if url:
                return str(url)
    return None


def _release_from_payload(payload: dict) -> ReleaseInfo | None:
    if payload.get("draft"):
        return None
    tag = str(payload.get("tag_name") or "").strip()
    download_url = _release_asset_url(payload)
    if not tag or not download_url:
        return None
    return ReleaseInfo(
        tag=tag,
        version=tag.lstrip("vV"),
        download_url=download_url,
        html_url=str(payload.get("html_url") or ""),
    )


def _github_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                "Nenhum Release encontrado no GitHub. Publique uma tag vX.Y.Z."
            ) from exc
        raise RuntimeError(f"Falha ao consultar GitHub ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Sem conexão para verificar atualização: {exc.reason}") from exc


def pick_latest_release(items: list[dict]) -> ReleaseInfo:
    """Escolhe o Release estável com a maior versão e o asset do instalador."""
    candidates: list[ReleaseInfo] = []
    for item in items:
        if not isinstance(item, dict) or item.get("prerelease"):
            continue
        release = _release_from_payload(item)
        if release is not None:
            candidates.append(release)

    if not candidates:
        raise RuntimeError(
            f"Nenhum Release estável com o asset {ASSET_NAME} foi encontrado."
        )
    return max(candidates, key=lambda item: parse_version(item.version))


def fetch_latest_release() -> ReleaseInfo:
    """Escolhe o Release publicado com a maior versão semântica."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=20"
    payload = _github_json(api_url)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Nenhum Release encontrado no GitHub. Publique uma tag vX.Y.Z.")

    latest = pick_latest_release(payload)
    logger.info(
        "Release mais recente: %s (local %s, atualiza=%s)",
        latest.tag,
        APP_VERSION,
        is_newer(latest.version),
    )
    return latest


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


def build_update_batch(
    installer_path: Path,
    app_exe: Path,
    log_path: Path,
) -> str:
    """Gera o .bat elevado: fecha o app, instala sem reabrir, depois inicia uma vez."""
    inno_log = Path(tempfile.gettempdir()) / INNO_LOG_NAME
    installer = str(installer_path)
    exe_fallback = str(app_exe)
    log = str(log_path)
    return "\r\n".join(
        [
            "@echo off",
            "setlocal EnableDelayedExpansion",
            f'set "LOG={log}"',
            'echo %DATE% %TIME% update_start> "%LOG%"',
            f'echo installer={installer}>> "%LOG%"',
            f'echo app={exe_fallback}>> "%LOG%"',
            'echo Killing running app>> "%LOG%"',
            f'taskkill /F /IM {APP_EXE_NAME} >> "%LOG%" 2>&1',
            "set /a WAITED=0",
            ":wait_close",
            f'tasklist /FI "IMAGENAME eq {APP_EXE_NAME}" | find /I "{APP_EXE_NAME}" >nul',
            "if not errorlevel 1 (",
            "  if !WAITED! GEQ 30 (",
            '    echo timeout_waiting_for_exit>> "%LOG%"',
            "    goto run_installer",
            "  )",
            "  timeout /t 1 /nobreak >nul",
            "  set /a WAITED+=1",
            "  goto wait_close",
            ")",
            ":run_installer",
            'echo running_installer>> "%LOG%"',
            (
                f'"{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
                f"/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS "
                f'/LOG="{inno_log}" >> "%LOG%" 2>&1'
            ),
            "set ERR=%ERRORLEVEL%",
            'echo installer_exit=%ERR%>> "%LOG%"',
            "timeout /t 2 /nobreak >nul",
            f'set "TARGET=%ProgramFiles%\\MPPSync\\{APP_EXE_NAME}"',
            'if exist "%TARGET%" (',
            '  start "" "%TARGET%"',
            '  echo restarted=%TARGET%>> "%LOG%"',
            f') else if exist "{exe_fallback}" (',
            f'  start "" "{exe_fallback}"',
            '  echo restarted_fallback>> "%LOG%"',
            ") else (",
            '  echo exe_missing>> "%LOG%"',
            ")",
            'echo update_done>> "%LOG%"',
        ]
    ) + "\r\n"


def launch_installer(installer_path: Path, app_exe: Path | None = None) -> Path:
    """Inicia o instalador elevado; retorna o caminho do log de update.

    Não encerra o app atual: o .bat elevado mata o processo depois do UAC.
    Se o UAC for cancelado, o app continua aberto.
    """
    if os.name != "nt":
        raise RuntimeError("Atualização automática só está disponível no Windows.")

    import ctypes

    exe_path = app_exe or resolve_app_exe()
    log_path = Path(tempfile.gettempdir()) / "mppsync_update.log"
    bat_path = Path(tempfile.gettempdir()) / "mppsync_update.bat"
    bat_path.write_text(
        build_update_batch(installer_path, exe_path, log_path),
        encoding="utf-8",
    )

    # SW_HIDE = 0: o cmd não pisca; o UAC do runas ainda aparece.
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(bat_path),
        None,
        str(bat_path.parent),
        0,
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
