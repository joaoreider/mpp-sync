"""Inicialização automática do app no Windows."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

APP_NAME = "MppEtlWatcher"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_supported() -> bool:
    return platform.system() == "Windows"


def build_startup_command() -> str:
    """Monta comando para iniciar a GUI sem console quando possível."""
    project_dir = Path(__file__).resolve().parent
    main_py = project_dir / "main.py"
    executable = _pythonw_executable()
    return f'"{executable}" "{main_py}"'


def is_enabled() -> bool:
    if not is_supported():
        return False

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            value, _value_type = winreg.QueryValueEx(key, APP_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False

    return value == build_startup_command()


def enable(command: str | None = None) -> None:
    if not is_supported():
        raise RuntimeError("Inicialização automática só está disponível no Windows.")

    import winreg

    startup_command = command or build_startup_command()
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command)


def disable() -> None:
    if not is_supported():
        return

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        return


def _pythonw_executable() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        return str(executable)
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        return str(pythonw)
    return os.fspath(executable)
