import logging

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
