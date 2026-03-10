import logging
import os

def setup_logger(name="jeeves"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    # File Handler
    fh = logging.FileHandler(os.path.join("logs", "app.log"), encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    # Add handlers to logger
    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger

# Global logger instance
logger = setup_logger()
