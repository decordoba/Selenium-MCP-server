import io
import logging
import os
import sys


def get_logger(logger_name: str, file_name: str = "log.log", folder_name: str = "logs"):
    # Configure logging
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    # Ensure the logs directory exists
    os.makedirs(folder_name, exist_ok=True)

    # File handler with DEBUG level
    file_handler = logging.FileHandler(f"{folder_name}/{file_name}", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s/%(funcName)s: %(message)s"
        )
    )
    logger.addHandler(file_handler)

    # Prevent errors with unicode characters in stdout
    # Without it the code gets stuck when logging a string with non ascii characters
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    # Console handler with INFO level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s/%(funcName)s: %(message)s"
        )
    )
    logger.addHandler(console_handler)

    return logger
