from src.utils.logger import get_logger

logger = get_logger(__name__)


def stream_output(text: str, end: str = "\n") -> None:
    print(text, end=end, flush=True)


def log_status(msg: str) -> None:
    logger.info(msg)
