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

    original_data = main_mod.DATA_DIR
    original_sys_data = system_mod.DATA_DIR

    main_mod.DATA_DIR = test_data
    system_mod.DATA_DIR = test_data

    yield test_data

    main_mod.DATA_DIR = original_data
    system_mod.DATA_DIR = original_sys_data


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

    def test_model_ready_is_false_initially(self, client):
        """Model reports not ready before ASR model loading."""
        resp = client.get("/api/system/health")
        assert resp.json()["model_ready"] is False


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

    def test_ready_false_when_model_not_loaded(self, client):
        """Ready is false when ASR model is not loaded."""
        resp = client.get("/api/system/capabilities")
        data = resp.json()
        assert data["ready"] is False

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
