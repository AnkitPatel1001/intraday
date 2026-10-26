""".env loading: root then backend/.env, never overriding real env vars."""

from __future__ import annotations

import os

from app.core.config import load_env_files


def _setup(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (tmp_path / ".env").write_text(
        "PROBE_KEY=root\nPROBE_ONLY=root\n", encoding="utf-8")
    (backend_dir / ".env").write_text(
        "PROBE_KEY=backend\nPROBE_BACKEND_ONLY=x\n", encoding="utf-8")
    for key in ("PROBE_KEY", "PROBE_ONLY", "PROBE_BACKEND_ONLY", "PROBE_EXISTING"):
        monkeypatch.delenv(key, raising=False)
    return backend_dir


def test_loads_root_then_backend_files(tmp_path, monkeypatch):
    backend_dir = _setup(tmp_path, monkeypatch)
    load_env_files(backend_dir)
    # backend/.env wins over root for same key
    assert os.environ["PROBE_KEY"] == "backend"
    assert os.environ["PROBE_ONLY"] == "root"
    assert os.environ["PROBE_BACKEND_ONLY"] == "x"


def test_existing_env_var_never_overridden(tmp_path, monkeypatch):
    backend_dir = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("PROBE_EXISTING", "shell_value")
    (backend_dir / ".env").write_text("PROBE_EXISTING=file_value\n", encoding="utf-8")
    load_env_files(backend_dir)
    assert os.environ["PROBE_EXISTING"] == "shell_value"


def test_missing_files_are_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("PROBE_NOFILE", raising=False)
    load_env_files(tmp_path / "nowhere")  # no files exist
    assert "PROBE_NOFILE" not in os.environ