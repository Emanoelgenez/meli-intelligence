import logging
from pathlib import Path
import runpy

import dotenv
import pytest

import meli_intelligence
from meli_intelligence.config.settings import (
    BRONZE_DIR,
    DATA_DIR,
    GOLD_DIR,
    PROJECT_ROOT,
    SILVER_DIR,
)
from meli_intelligence.logging_config import LOGGER_NAME, configure_logging


def test_package_can_be_imported() -> None:
    assert meli_intelligence.__version__ == "0.1.0"


def test_project_and_data_paths() -> None:
    assert PROJECT_ROOT.is_dir()
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert BRONZE_DIR == DATA_DIR / "bronze"
    assert SILVER_DIR == DATA_DIR / "silver"
    assert GOLD_DIR == DATA_DIR / "gold"


def test_configure_logging_sets_level_and_handler_once() -> None:
    logger = configure_logging("DEBUG")
    initial_handler_count = len(logger.handlers)

    assert isinstance(logger, logging.Logger)
    assert logger.name == LOGGER_NAME
    assert logger.level == logging.DEBUG
    assert initial_handler_count >= 1

    configure_logging("WARNING")

    assert logger.level == logging.WARNING
    assert len(logger.handlers) == initial_handler_count


@pytest.mark.parametrize("explicit", [False, True])
def test_settings_root_and_dotenv_are_independent_of_working_directory(tmp_path, monkeypatch, explicit):
    source_root = Path(__file__).resolve().parents[2]
    expected = tmp_path / "application" if explicit else source_root
    if explicit:
        expected.mkdir()
        (expected / ".env").write_text("MELI_TEST_ROOT_SENTINEL=from_application\n", encoding="utf-8")
        # Non-canonical input must still become an absolute, resolved Path.
        monkeypatch.setenv("MELI_PROJECT_ROOT", str(expected / ".." / expected.name))
    else:
        monkeypatch.delenv("MELI_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("MELI_TEST_ROOT_SENTINEL", raising=False)
    monkeypatch.chdir(tmp_path)
    calls = []
    load_dotenv = dotenv.load_dotenv

    def record_dotenv(path):
        calls.append(path)
        # Keep any dotenv environment mutations local to this test.
        with monkeypatch.context() as env:
            import os
            env.setattr(os, "environ", os.environ.copy())
            result = load_dotenv(path)
            if explicit:
                assert os.getenv("MELI_TEST_ROOT_SENTINEL") == "from_application"
            return result

    monkeypatch.setattr(dotenv, "load_dotenv", record_dotenv)
    settings = runpy.run_path(str(source_root / "src/meli_intelligence/config/settings.py"))
    assert settings["PROJECT_ROOT"] == expected.resolve()
    assert settings["PROJECT_ROOT"].is_absolute()
    assert calls == [expected / ".env"]
    assert settings["DATA_DIR"] == expected / "data"
    for name in ("BRONZE", "SILVER", "GOLD"):
        assert settings[f"{name}_DIR"] == expected / "data" / name.lower()
