import logging
import sys

from config.settings import config

LOG_LEVEL = config.LOG_LEVEL
LOG_FORMAT = config.LOG_FORMAT


def _build_stream_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(LOG_LEVEL)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    return handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        logger.addHandler(_build_stream_handler())
        logger.propagate = False
    return logger
