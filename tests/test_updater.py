"""Testes do fluxo de atualização (sem Windows/GitHub)."""

from pathlib import Path

from updater import (
    APP_EXE_NAME,
    ASSET_NAME,
    build_update_batch,
    is_newer,
    parse_version,
    pick_latest_release,
    _release_from_payload,
)


def test_parse_version_strips_v_prefix():
    assert parse_version("v1.0.13") == (1, 0, 13)
    assert parse_version("1.0.9") == (1, 0, 9)


def test_is_newer_compares_numeric_segments():
    assert is_newer("1.0.13", "1.0.9") is True
    assert is_newer("1.0.13", "1.0.13") is False
    assert is_newer("1.0.12", "1.0.13") is False


def test_update_batch_kills_app_and_does_not_ask_inno_to_restart():
    content = build_update_batch(
        Path(r"C:\Temp\MPPSync-Setup.exe"),
        Path(r"C:\Program Files\MPPSync\MPPSync.exe"),
        Path(r"C:\Temp\mppsync_update.log"),
    )
    assert f"taskkill /F /IM {APP_EXE_NAME}" in content
    assert "/NOCLOSEAPPLICATIONS" in content
    assert "/NORESTARTAPPLICATIONS" in content
    assert "/FORCECLOSEAPPLICATIONS" not in content
    assert content.count('start ""') == 2
    assert f"%ProgramFiles%\\MPPSync\\{APP_EXE_NAME}" in content


def test_pick_latest_release_uses_highest_semver_not_list_order():
    def item(tag: str) -> dict:
        return {
            "tag_name": tag,
            "html_url": f"https://example/{tag}",
            "assets": [{"name": ASSET_NAME, "browser_download_url": f"https://example/{tag}.exe"}],
        }

    latest = pick_latest_release([item("v1.0.9"), item("v1.0.13"), item("v1.0.10")])
    assert latest.version == "1.0.13"


def test_release_from_payload_requires_setup_asset():
    payload = {
        "tag_name": "v1.0.14",
        "html_url": "https://github.com/joaoreider/mpp-sync/releases/tag/v1.0.14",
        "assets": [{"name": ASSET_NAME, "browser_download_url": "https://example/setup.exe"}],
    }
    release = _release_from_payload(payload)
    assert release is not None
    assert release.version == "1.0.14"
    assert _release_from_payload({"tag_name": "v1.0.14", "assets": []}) is None
    assert _release_from_payload({"draft": True, **payload}) is None
