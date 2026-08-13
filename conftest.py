from pathlib import Path
import json
import pytest


@pytest.fixture(scope="session")
def framework_config() -> dict:
    """Load lightweight framework config without extra dependencies."""
    config_path = Path(__file__).parent / "config" / "framework_config.yaml"
    data: dict[str, str] = {}

    # Keep parser intentionally minimal for Day-1: key: value pairs only.
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")

    return data


@pytest.fixture(scope="session")
def artifact_folder() -> Path:
    path = Path("reports")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def session_metadata(artifact_folder: Path) -> Path:
    meta_path = artifact_folder / "session_metadata.json"
    payload = {"framework": "desktop-automation-poc", "stage": "day-1"}
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return meta_path
