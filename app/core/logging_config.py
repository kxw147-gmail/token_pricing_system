import logging
import os
from app.core.config import settings

def setup_logging():
    """
    Sets up the logging configuration for the application.
    Logs to console and a file.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Create logs directory if it doesn't exist
    log_file_dir = os.path.dirname(settings.LOG_FILE_PATH)
    if log_file_dir and not os.path.exists(log_file_dir):
        os.makedirs(log_file_dir)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(), # Console handler
            logging.FileHandler(settings.LOG_FILE_PATH) # File handler
        ]
    )

    # Optional: Set higher log level for specific noisy libraries
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('asyncio_rate_limit').setLevel(logging.WARNING)

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level) # Ensure root logger level is set

    # Add a custom filter to ensure `uvicorn` logs also go to file
    # FastAPI's Uvicorn logging can be tricky to capture fully without this
    # if you're not using their default config dict setup.
    class NoisyUvicornFilter(logging.Filter):
        def filter(self, record):
            # Exclude uvicorn access logs from the main app.log if desired,
            # or simply allow them through for full logging.
            # For simplicity, we're allowing them.
            return True

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.addFilter(NoisyUvicornFilter())

    logging.info(f"Logging configured at level: {settings.LOG_LEVEL.upper()}")
    logging.info(f"Logs will also be written to: {settings.LOG_FILE_PATH}")