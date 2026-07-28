"""Atualização do app a partir dos Releases do GitHub."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.5"
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


def _installed_app_exe() -> Path:
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    return Path(program_files) / "MPPSync" / "MPPSync.exe"


def launch_installer(installer_path: Path) -> None:
    """Inicia o instalador elevado, aguarda e reabre o app ao concluir."""
    if os.name != "nt":
        raise RuntimeError("Atualização automática só está disponível no Windows.")

    import ctypes

    app_exe = _installed_app_exe()
    bat_path = Path(tempfile.gettempdir()) / "mppsync_update.bat"
    bat_content = "\r\n".join(
        [
            "@echo off",
            f'"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS',
            "if errorlevel 1 exit /b 1",
            f'if exist "{app_exe}" start "" "{app_exe}"',
        ]
    ) + "\r\n"
    bat_path.write_text(bat_content, encoding="utf-8")

    # SW_HIDE = 0; retorno > 32 indica sucesso ao pedir elevação.
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        "cmd.exe",
        f'/c ""{bat_path}""',
        None,
        0,
    )
    if result <= 32:
        raise RuntimeError(
            "Não foi possível iniciar o instalador (UAC cancelado ou falha). "
            "Baixe o Release e execute MPPSync-Setup.exe como administrador."
        )
    logger.info("Instalador de atualização iniciado (ShellExecute=%s)", result)
