"""Tests for system endpoints (health, capabilities) and SPA serving."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# We need to set env vars before importing the app
os.environ.setdefault("NANOSCRIBE_DATA_DIR", "/tmp/nanoscribe-test-data")
os.environ.setdefault("NANOSCRIBE_STATIC_DIR", "/tmp/nanoscribe-test-static")

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def setup_data_dir(tmp_path: Path):
    """Use a temp directory for each test to avoid side effects."""
    test_data = tmp_path / "data"
    test_data.mkdir()
    (test_data / "memos").mkdir()

    # Patch the module-level constants
    import app.api.system as system_mod
    import app.main as main_mod
    import app.services.status as status_mod

    original_data = main_mod.DATA_DIR
    original_sys_data = system_mod.DATA_DIR
    original_status_data = status_mod.DATA_DIR

    main_mod.DATA_DIR = test_data
    system_mod.DATA_DIR = test_data
    status_mod.DATA_DIR = test_data

    # Clean engine settings from the shared test DB so no test
    # sees stale remote-engine data from a previous test run.
    _clean_engine_settings()

    yield test_data

    main_mod.DATA_DIR = original_data
    system_mod.DATA_DIR = original_sys_data
    status_mod.DATA_DIR = original_status_data

    # Clean up again after the test
    _clean_engine_settings()


def _clean_engine_settings() -> None:
    """Remove all system_settings rows and reset the models singleton."""
    from app.core.config import get_settings
    from app.services.transcription import reset_models

    db_path = get_settings().db_path
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("DELETE FROM system_settings")
            conn.commit()
            conn.close()
        except Exception:
            pass
    reset_models()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """VAL-SYS-003: Health endpoint returns component-level status."""

    def test_health_returns_200(self, client):
        """Health endpoint returns HTTP 200."""
        resp = client.get("/api/system/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self, client):
        """Health response has backend, db, storage, model_ready fields."""
        resp = client.get("/api/system/health")
        data = resp.json()
        assert "backend" in data
        assert "db" in data
        assert "storage" in data
        assert "model_ready" in data

    def test_backend_is_ok(self, client):
        """Backend reports ok when FastAPI is serving."""
        resp = client.get("/api/system/health")
        assert resp.json()["backend"] == "ok"

    def test_db_is_ok_when_accessible(self, client, setup_data_dir):
        """DB reports ok when SQLite file is accessible and has expected schema."""
        db_path = setup_data_dir / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS memos (id TEXT PRIMARY KEY)")
        conn.close()

        resp = client.get("/api/system/health")
        assert resp.json()["db"] == "ok"

    def test_storage_is_ok_when_writable(self, client):
        """Storage reports ok when data dir is writable."""
        resp = client.get("/api/system/health")
        assert resp.json()["storage"] == "ok"

    def test_model_ready_is_false_initially(self, client, tmp_path):
        """Model reports not ready when no models are cached."""
        import app.services.capabilities as cap_mod

        original = cap_mod._get_modelscope_cache_dir
        cap_mod._get_modelscope_cache_dir = lambda: tmp_path / "empty_cache"  # ty:ignore[invalid-assignment]
        try:
            resp = client.get("/api/system/health")
            assert resp.json()["model_ready"] is False
        finally:
            cap_mod._get_modelscope_cache_dir = original


class TestHealthDegradation:
    """VAL-SYS-004: Health degrades gracefully when components are unavailable."""

    def test_health_still_200_when_db_corrupt(self, client, setup_data_dir):
        """Health returns 200 even when DB file is corrupt."""
        # Write invalid content to the DB file to simulate corruption
        db_path = setup_data_dir / "nanoscribe.db"
        db_path.write_text("this is not a sqlite database")

        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["db"] == "error"

    def test_health_reports_db_error_when_file_missing(self, client, setup_data_dir):
        """Health reports db error when the DB file does not exist.

        sqlite3.connect() would create a new empty file, but check_db_health()
        must detect that the file was not there and report error.
        """
        db_path = setup_data_dir / "nanoscribe.db"
        assert not db_path.exists(), "DB file should not exist for this test"

        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["db"] == "error"

    def test_health_reports_db_error_when_empty_schema(self, client, setup_data_dir):
        """Health reports db error when DB exists but has no expected tables.

        An empty SQLite database (no memos table) indicates the schema
        was not properly initialized.
        """
        db_path = setup_data_dir / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS wrong_table (id INTEGER)")
        conn.close()

        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["db"] == "error"

    def test_health_reports_db_ok_with_correct_schema(self, client, setup_data_dir):
        """Health reports db ok when DB has the expected memos table."""
        db_path = setup_data_dir / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS memos (id TEXT PRIMARY KEY)")
        conn.close()

        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["db"] == "ok"

    def test_health_still_200_when_storage_readonly(self, client, setup_data_dir):
        """Health returns 200 even when storage is read-only."""
        # Make data dir read-only
        os.chmod(str(setup_data_dir), 0o444)
        try:
            resp = client.get("/api/system/health")
            assert resp.status_code == 200
            assert resp.json()["storage"] == "error"
        finally:
            os.chmod(str(setup_data_dir), 0o755)


class TestSPAServing:
    """VAL-SYS-011: Single Docker deployment serves frontend and backend."""

    def test_root_returns_html(self, client):
        """GET / returns HTML content."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_root_returns_nanoscribe_content(self, client):
        """GET / returns NanoScribe branded content."""
        resp = client.get("/")
        assert "NanoScribe" in resp.text

    def test_api_health_returns_json(self, client):
        """GET /api/system/health returns JSON."""
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")


class TestPathTraversalProtection:
    """serve_spa() must prevent path-traversal attacks."""

    def test_resolve_path_rejects_traversal(self):
        """_resolve_path returns None for paths escaping the base directory."""
        from app.main import _resolve_path

        assert _resolve_path("/tmp/test-static", "../../../etc/passwd") is None
        assert _resolve_path("/tmp/test-static", "../../etc/shadow") is None
        assert _resolve_path("/tmp/test-static", "/etc/passwd") is None

    def test_resolve_path_accepts_valid_files(self):
        """_resolve_path returns the resolved path for valid relative paths."""
        from app.main import _resolve_path

        result = _resolve_path("/tmp/test-static", "favicon.png")
        assert result == "/tmp/test-static/favicon.png"

    def test_resolve_path_accepts_subdirs(self):
        """_resolve_path accepts paths with subdirectories."""
        from app.main import _resolve_path

        result = _resolve_path("/tmp/test-static", "assets/icon.svg")
        assert result == "/tmp/test-static/assets/icon.svg"

    def test_resolve_path_rejects_absolute_path(self):
        """_resolve_path rejects absolute paths outside the base dir."""
        from app.main import _resolve_path

        assert _resolve_path("/tmp/test-static", "/absolute/path") is None

    def test_traversal_request_returns_fallback(self, client):
        """Requests with path traversal still return 200 (SPA fallback), not arbitrary files."""
        resp = client.get("/../../../etc/passwd")
        # The SPA fallback is served rather than an arbitrary file
        assert resp.status_code == 200


class TestDataDirectory:
    """VAL-SYS-012: All persistent data stored under /app/data."""

    def test_data_dir_created_on_start(self, setup_data_dir):
        """Data directory and memos subdirectory exist."""
        assert setup_data_dir.is_dir()
        assert (setup_data_dir / "memos").is_dir()


class TestAPIPrefix:
    """VAL-SYS-013: API routes live under /api prefix."""

    def test_system_health_under_api(self, client):
        """System health is accessible at /api/system/health."""
        resp = client.get("/api/system/health")
        assert resp.status_code == 200

    def test_root_not_json(self, client):
        """Root path returns HTML, not JSON."""
        resp = client.get("/")
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "application/json" not in ct


# ---------------------------------------------------------------------------
# VAL-SYS-001 & VAL-SYS-002: Capability manifest endpoint
# ---------------------------------------------------------------------------
class TestCapabilitiesEndpoint:
    """VAL-SYS-001: Capability manifest endpoint returns complete runtime manifest."""

    def test_capabilities_returns_200(self, client):
        """Capabilities endpoint returns HTTP 200."""
        resp = client.get("/api/system/capabilities")
        assert resp.status_code == 200

    def test_capabilities_returns_json(self, client):
        """Capabilities endpoint returns JSON."""
        resp = client.get("/api/system/capabilities")
        assert "application/json" in resp.headers.get("content-type", "")

    def test_capabilities_has_all_required_keys(self, client):
        """Response contains all required keys."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        required_keys = [
            "ready",
            "gpu",
            "device",
            "asr_model",
            "vad",
            "timestamps",
            "speaker_diarization",
            "hotwords",
            "language_auto_detect",
            "recording",
        ]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

    def test_boolean_fields_are_booleans(self, client):
        """Boolean capability flags have true/false values."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        boolean_keys = [
            "ready",
            "gpu",
            "timestamps",
            "speaker_diarization",
            "hotwords",
            "language_auto_detect",
            "recording",
        ]
        for key in boolean_keys:
            assert isinstance(data[key], bool), f"Key '{key}' should be boolean, got {type(data[key])}"

    def test_string_fields_are_strings(self, client):
        """String metadata fields are strings."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        string_keys = ["device", "asr_model", "vad"]
        for key in string_keys:
            assert isinstance(data[key], str), f"Key '{key}' should be string, got {type(data[key])}"


class TestCapabilitiesRuntimeState:
    """VAL-SYS-002: Capability manifest reflects actual runtime state."""

    def test_gpu_false_when_no_cuda(self, client):
        """Without CUDA, gpu is false and device indicates CPU."""
        import importlib

        import app.services.capabilities as cap_mod

        with patch.dict("sys.modules", {"torch": None}):
            # Force re-detection with torch unavailable
            importlib.reload(cap_mod)

            resp = client.get("/api/system/capabilities")
            data = resp.json()
            assert data["gpu"] is False
            assert data["device"] == "cpu"

        # Restore real module
        importlib.reload(cap_mod)

    def test_gpu_true_when_cuda_available(self, client):
        """With CUDA available, gpu is true and device contains cuda info."""
        from unittest.mock import MagicMock

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "NVIDIA RTX 3070"
        mock_torch.cuda.device_count.return_value = 1

        import importlib

        import app.services.capabilities as cap_mod

        with patch.dict("sys.modules", {"torch": mock_torch}):
            importlib.reload(cap_mod)

            resp = client.get("/api/system/capabilities")
            data = resp.json()
            assert data["gpu"] is True
            assert "cuda" in data["device"].lower() or "nvidia" in data["device"].lower()

        # Restore real module
        importlib.reload(cap_mod)

    def test_ready_false_when_model_not_loaded(self, client, tmp_path):
        """Ready is false when model cache directories are empty."""
        import app.services.capabilities as cap_mod

        original = cap_mod._get_modelscope_cache_dir
        cap_mod._get_modelscope_cache_dir = lambda: tmp_path / "empty_cache"  # ty:ignore[invalid-assignment]
        try:
            resp = client.get("/api/system/capabilities")
            data = resp.json()
            assert data["ready"] is False
        finally:
            cap_mod._get_modelscope_cache_dir = original

    def test_asr_model_is_nonempty_string(self, client):
        """ASR model identifier is a non-empty string."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        assert isinstance(data["asr_model"], str)
        assert len(data["asr_model"]) > 0

    def test_vad_model_is_nonempty_string(self, client):
        """VAD model identifier is a non-empty string."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        assert isinstance(data["vad"], str)
        assert len(data["vad"]) > 0


class TestCentralizedConfig:
    """All env vars read through core/config.py Settings class."""

    def test_settings_reads_data_dir(self):
        """Settings reads NANOSCRIBE_DATA_DIR."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.data_dir == Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))

    def test_settings_reads_static_dir(self):
        """Settings reads NANOSCRIBE_STATIC_DIR."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.static_dir == Path(os.environ.get("NANOSCRIBE_STATIC_DIR", "/app/static"))

    def test_settings_db_path_derived(self):
        """db_path is derived from data_dir."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.db_path == settings.data_dir / "nanoscribe.db"

    def test_main_imports_settings(self):
        """main.py imports from core.config rather than reading os.environ directly."""
        import inspect

        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "get_settings" in source
        assert "os.environ" not in source

    def test_system_api_imports_settings(self):
        """api/system.py imports from core.config rather than reading os.environ directly."""
        import inspect

        import app.api.system as system_mod

        source = inspect.getsource(system_mod)
        assert "get_settings" in source
        assert "os.environ" not in source

    def test_migrate_imports_settings(self):
        """db/migrate.py imports from core.config rather than reading os.environ directly."""
        import inspect

        import app.db.migrate as migrate_mod

        source = inspect.getsource(migrate_mod)
        assert "core.config" in source
        # os.environ should only appear in config.py, not migrate.py
        assert "os.environ" not in source


class TestDBConnectionDeduplication:
    """Single source of DB connection helpers in db/__init__.py."""

    def test_db_module_has_db_connection(self):
        """db/__init__.py provides db_connection."""
        from app.db import db_connection

        assert callable(db_connection)

    def test_dependencies_no_longer_has_get_db_connection(self):
        """core/dependencies.py no longer exports get_db_connection."""
        import app.core.dependencies as deps

        assert not hasattr(deps, "get_db_connection")

    def test_db_connection_works(self, tmp_path):
        """db_connection context manager provides a working SQLite connection."""
        from app.db import db_connection

        db_path = tmp_path / "test.db"
        with db_connection(db_path) as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0] == "wal"
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1


# ---------------------------------------------------------------------------
# Status endpoint tests
# ---------------------------------------------------------------------------
class TestStatusEndpoint:
    """GET /api/system/status returns runtime status info."""

    def test_status_returns_200(self, client):
        """Status endpoint returns HTTP 200."""
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

    def test_status_has_required_fields(self, client):
        """Status response has all required fields."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "device" in data
        assert "gpu_available" in data
        assert "data_dir" in data
        assert "memo_count" in data
        assert "storage_used_mb" in data
        assert "models_cached" in data

    def test_status_field_is_string(self, client):
        """Status field is a non-empty string."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["status"], str)
        assert data["status"] in ("ready", "loading", "error")

    def test_device_is_string(self, client):
        """Device field is a string."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["device"], str)
        assert len(data["device"]) > 0

    def test_gpu_available_is_boolean(self, client):
        """gpu_available is a boolean."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["gpu_available"], bool)

    def test_memo_count_is_int(self, client):
        """memo_count is an integer."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["memo_count"], int)
        assert data["memo_count"] >= 0

    def test_storage_used_mb_is_number(self, client):
        """storage_used_mb is a number."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["storage_used_mb"], (int, float))
        assert data["storage_used_mb"] >= 0

    def test_models_cached_is_list(self, client):
        """models_cached is a list of strings."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["models_cached"], list)
        for model in data["models_cached"]:
            assert isinstance(model, str)

    def test_data_dir_is_string(self, client):
        """data_dir is a string path."""
        resp = client.get("/api/system/status")
        data = resp.json()
        assert isinstance(data["data_dir"], str)
        assert len(data["data_dir"]) > 0

    def test_memo_count_zero_when_no_db(self, client, setup_data_dir):
        """memo_count is 0 when no DB file exists."""
        db_path = setup_data_dir / "nanoscribe.db"
        assert not db_path.exists()
        resp = client.get("/api/system/status")
        assert resp.json()["memo_count"] == 0

    def test_memo_count_matches_db(self, client, setup_data_dir):
        """memo_count reflects actual memo rows in the database."""
        db_path = setup_data_dir / "nanoscribe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS memos (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO memos (id) VALUES ('test-1')")
        conn.execute("INSERT INTO memos (id) VALUES ('test-2')")
        conn.commit()
        conn.close()

        resp = client.get("/api/system/status")
        assert resp.json()["memo_count"] == 2


# ---------------------------------------------------------------------------
# Readiness endpoint tests
# ---------------------------------------------------------------------------
class TestReadinessEndpoint:
    """GET /api/system/readiness returns per-model readiness status."""

    def test_readiness_returns_200(self, client):
        """Readiness endpoint returns HTTP 200."""
        resp = client.get("/api/system/readiness")
        assert resp.status_code == 200

    def test_readiness_has_required_fields(self, client):
        """Readiness response has all required top-level fields."""
        resp = client.get("/api/system/readiness")
        data = resp.json()
        assert "ready" in data
        assert "models" in data
        assert "device" in data
        assert "gpu_available" in data

    def test_readiness_models_has_all_keys(self, client):
        """Models dict has asr, vad, punc, diarization keys."""
        resp = client.get("/api/system/readiness")
        data = resp.json()
        for key in ("asr", "vad", "punc", "diarization"):
            assert key in data["models"], f"Missing model key: {key}"

    def test_readiness_model_entries_have_required_fields(self, client):
        """Each model entry has name, loaded, downloading fields."""
        resp = client.get("/api/system/readiness")
        data = resp.json()
        for key, model_info in data["models"].items():
            assert "name" in model_info, f"Missing 'name' for model {key}"
            assert "loaded" in model_info, f"Missing 'loaded' for model {key}"
            assert "downloading" in model_info, f"Missing 'downloading' for model {key}"
            assert isinstance(model_info["loaded"], bool)
            assert isinstance(model_info["downloading"], bool)
            assert isinstance(model_info["name"], str)

    def test_readiness_ready_is_boolean(self, client):
        """ready field is a boolean."""
        resp = client.get("/api/system/readiness")
        assert isinstance(resp.json()["ready"], bool)

    def test_readiness_gpu_available_is_boolean(self, client):
        """gpu_available field is a boolean."""
        resp = client.get("/api/system/readiness")
        assert isinstance(resp.json()["gpu_available"], bool)

    def test_readiness_device_is_string(self, client):
        """device field is a non-empty string."""
        resp = client.get("/api/system/readiness")
        data = resp.json()
        assert isinstance(data["device"], str)
        assert len(data["device"]) > 0

    def test_readiness_not_ready_when_no_cache(self, client, tmp_path):
        """Readiness reports not ready when model cache directories don't exist."""
        import app.services.capabilities as cap_mod

        original = cap_mod._get_modelscope_cache_dir
        cap_mod._get_modelscope_cache_dir = lambda: tmp_path / "nonexistent_cache"  # ty:ignore[invalid-assignment]

        try:
            resp = client.get("/api/system/readiness")
            data = resp.json()
            assert data["ready"] is False
            for model_info in data["models"].values():
                assert model_info["loaded"] is False
                assert model_info["downloading"] is False
        finally:
            cap_mod._get_modelscope_cache_dir = original

    def test_readiness_shows_downloading_when_empty_dir(self, client, tmp_path):
        """Readiness reports downloading=True when model dir exists but has no files."""
        import app.services.capabilities as cap_mod

        cache_dir = tmp_path / "ms_cache"
        # Create empty VAD model directory
        vad_dir = cache_dir / "models" / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch"
        vad_dir.mkdir(parents=True)

        original = cap_mod._get_modelscope_cache_dir
        cap_mod._get_modelscope_cache_dir = lambda: cache_dir  # ty:ignore[invalid-assignment]

        try:
            resp = client.get("/api/system/readiness")
            data = resp.json()
            assert data["ready"] is False
            assert data["models"]["vad"]["downloading"] is True
            assert data["models"]["vad"]["loaded"] is False
        finally:
            cap_mod._get_modelscope_cache_dir = original

    def test_readiness_shows_cached_when_files_exist(self, client, tmp_path):
        """Readiness reports loaded=True (cached on disk) and downloading=False when files exist."""
        import app.services.capabilities as cap_mod

        cache_dir = tmp_path / "ms_cache"
        # Create VAD model directory with a file
        vad_dir = cache_dir / "models" / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch"
        vad_dir.mkdir(parents=True)
        (vad_dir / "model.pb").write_text("fake model")

        original = cap_mod._get_modelscope_cache_dir
        cap_mod._get_modelscope_cache_dir = lambda: cache_dir  # ty:ignore[invalid-assignment]

        try:
            resp = client.get("/api/system/readiness")
            data = resp.json()
            # loaded means cached on disk (not in-memory)
            assert data["models"]["vad"]["loaded"] is True
            # Not downloading because files already exist
            assert data["models"]["vad"]["downloading"] is False
        finally:
            cap_mod._get_modelscope_cache_dir = original

    def test_readiness_model_names(self, client):
        """Model names use friendly display names."""
        resp = client.get("/api/system/readiness")
        data = resp.json()
        assert data["models"]["asr"]["name"] == "Fun-ASR-Nano-2512"
        assert data["models"]["vad"]["name"] == "fsmn-vad"
        assert data["models"]["punc"]["name"] == "ct-punc"
        assert data["models"]["diarization"]["name"] == "CAM++"


# ---------------------------------------------------------------------------
# Engine settings endpoint tests
# ---------------------------------------------------------------------------
class TestEngineSettingsEndpoint:
    """GET/PUT /api/system/settings/engine for transcription engine config."""

    def _get_db_path(self) -> Path:
        """Return the DB path used by the API (derived from Settings)."""
        from app.core.config import get_settings

        return get_settings().db_path

    def setup_method(self) -> None:
        """Reset engine settings before each test for isolation."""
        db_path = self._get_db_path()
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("DELETE FROM system_settings")
        conn.commit()
        conn.close()

        from app.services.transcription import reset_models

        reset_models()

    @classmethod
    def teardown_class(cls) -> None:
        """Clean up engine settings after all tests in this class."""
        from app.core.config import get_settings
        from app.services.transcription import reset_models

        db_path = get_settings().db_path
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM system_settings")
        conn.commit()
        conn.close()
        reset_models()

    def test_get_engine_settings_returns_200(self, client):
        """GET /api/system/settings/engine returns HTTP 200."""
        resp = client.get("/api/system/settings/engine")
        assert resp.status_code == 200

    def test_get_engine_settings_has_required_fields(self, client):
        """Response contains engine, remote_url, remote_api_key, remote_model."""
        resp = client.get("/api/system/settings/engine")
        data = resp.json()
        assert "engine" in data
        assert "remote_url" in data
        assert "remote_api_key" in data
        assert "remote_model" in data

    def test_get_engine_settings_defaults_to_local(self, client):
        """Default engine is local when no remote URL is configured."""
        resp = client.get("/api/system/settings/engine")
        data = resp.json()
        assert data["engine"] == "local"
        assert data["remote_url"] == ""
        assert data["remote_model"] == "whisper-1"

    def test_api_key_masked_in_get(self, client):
        """API key is masked in GET response."""
        db_path = self._get_db_path()
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('engine', 'remote') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_url', 'https://api.openai.com/v1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_api_key', 'sk-secret-key') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_model', 'whisper-1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/system/settings/engine")
        data = resp.json()
        assert data["remote_api_key"] == "********"
        assert data["engine"] == "remote"

    def test_put_engine_settings_switches_to_remote(self, client):
        """PUT can switch engine to remote and persists to DB."""
        resp = client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_model": "whisper-1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "remote"
        assert data["remote_url"] == "https://api.openai.com/v1"

        # Verify persisted in DB
        db_path = self._get_db_path()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'engine'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "remote"

    def test_put_engine_settings_switches_to_local(self, client):
        """PUT can switch engine back to local."""
        # First switch to remote
        client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_model": "whisper-1",
            },
        )

        # Now switch to local
        resp = client.put(
            "/api/system/settings/engine",
            json={
                "engine": "local",
                "remote_url": "",
                "remote_model": "whisper-1",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["engine"] == "local"

    def test_put_remote_without_url_returns_422(self, client):
        """PUT with engine=remote but empty URL returns 422."""
        resp = client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "",
                "remote_model": "whisper-1",
            },
        )
        assert resp.status_code == 422
        assert "URL" in resp.json()["detail"]

    def test_put_preserves_api_key_when_masked(self, client):
        """PUT with masked API key placeholder preserves the existing key."""
        db_path = self._get_db_path()

        # Set up remote with an API key
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('engine', 'remote') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_url', 'https://api.openai.com/v1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_api_key', 'sk-original-key') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_model', 'whisper-1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.commit()
        conn.close()

        # Update with masked key — should preserve original
        resp = client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_api_key": "********",
                "remote_model": "whisper-1",
            },
        )
        assert resp.status_code == 200

        # Verify key preserved in DB
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'remote_api_key'").fetchone()
        conn.close()
        assert row[0] == "sk-original-key"

    def test_put_preserves_api_key_when_null(self, client):
        """PUT with remote_api_key=null preserves the existing key."""
        db_path = self._get_db_path()

        # Set up remote with an API key
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('engine', 'remote') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_url', 'https://api.openai.com/v1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_api_key', 'sk-original-key') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('remote_model', 'whisper-1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        conn.commit()
        conn.close()

        # Update with null key — should preserve original
        resp = client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_api_key": None,
                "remote_model": "whisper-1",
            },
        )
        assert resp.status_code == 200

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'remote_api_key'").fetchone()
        conn.close()
        assert row[0] == "sk-original-key"

    def test_put_preserves_remote_settings_on_local_switch(self, client):
        """Switching to local preserves remote URL/model in DB for easy switching back."""
        db_path = self._get_db_path()

        # First configure remote
        client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_api_key": "sk-test",
                "remote_model": "whisper-1",
            },
        )

        # Switch to local
        client.put(
            "/api/system/settings/engine",
            json={
                "engine": "local",
                "remote_url": "",
                "remote_model": "whisper-1",
            },
        )

        # Verify remote URL and API key still in DB
        conn = sqlite3.connect(str(db_path))
        url = conn.execute("SELECT value FROM system_settings WHERE key = 'remote_url'").fetchone()
        key = conn.execute("SELECT value FROM system_settings WHERE key = 'remote_api_key'").fetchone()
        conn.close()
        assert url[0] == "https://api.openai.com/v1"
        assert key[0] == "sk-test"

    def test_put_resets_models_singleton(self, client):
        """PUT resets the models singleton so next get_models() picks up new config."""
        from app.services.transcription import get_models, reset_models

        # Force local initialization
        reset_models()
        models_before = get_models()
        assert type(models_before).__name__ == "TranscriptionModels"

        # Switch to remote
        client.put(
            "/api/system/settings/engine",
            json={
                "engine": "remote",
                "remote_url": "https://api.openai.com/v1",
                "remote_api_key": "sk-test",
                "remote_model": "whisper-1",
            },
        )

        # After reset, get_models should return RemoteTranscriptionService
        models_after = get_models()
        assert type(models_after).__name__ == "RemoteTranscriptionService"

        # Clean up
        reset_models()
