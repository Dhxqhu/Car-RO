"""Shop branding sync for PDF headers."""

from pathlib import Path

import pytest

from carro.core import shop_branding as brandmod


@pytest.fixture()
def branding_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_dir = tmp_path / "carro"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.toml"
    cfg_file.write_text('shop_name = "(shop name here)"\nlogo_path = ""\n', encoding="utf-8")
    monkeypatch.setattr(brandmod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(brandmod, "META_FILE", cfg_dir / "shop_branding.json")
    monkeypatch.setattr("carro.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("carro.config.CONFIG_FILE", cfg_file)
    return cfg_dir


def test_apply_remote_sets_shop_name(branding_env):
    brandmod.apply_remote(
        {"shop_name": "Main Street Auto", "updated": "2026-08-17T12:00:00", "has_logo": False}
    )
    cfg = brandmod.load_config()
    assert cfg["shop_name"] == "Main Street Auto"
    meta = brandmod.load_meta()
    assert meta["source"] == "server"


def test_install_logo_bytes_updates_config(branding_env):
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    dest = brandmod.install_logo_bytes(png, suffix=".png")
    assert dest.is_file()
    cfg = brandmod.load_config()
    assert cfg["logo_path"] == str(dest)


def test_resolve_pdf_branding_uses_local_when_set(branding_env):
    brandmod.apply_local_name("Bay Auto", source="local")
    out = brandmod.resolve_pdf_branding(refresh_remote=False)
    assert out["shop_name"] == "Bay Auto"
