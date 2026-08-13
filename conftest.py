from pathlib import Path
import json
import logging
import pytest


@pytest.fixture(scope="session")
def framework_config() -> dict:
    """Load lightweight framework config without extra dependencies."""
    config_path = Path(__file__).parent / "config" / "framework_config.yaml"
    data: dict[str, str] = {}

    # Keep parser intentionally minimal: key: value pairs only.
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")

    return data


@pytest.fixture(scope="session", autouse=True)
def configure_framework_logging(framework_config: dict) -> None:
    """Initialise stdlib logging once per session from config. No test-specific logic."""
    level_name = framework_config.get("log_level", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@pytest.fixture(scope="session")
def artifact_folder() -> Path:
    path = Path("reports")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def session_metadata(artifact_folder: Path) -> Path:
    meta_path = artifact_folder / "session_metadata.json"
    payload = {"framework": "desktop-automation-poc", "stage": "day-2"}
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return meta_path
