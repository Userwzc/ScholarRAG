import logging
import sys
import os

# Configurable log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Only configure if no handlers are present
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVEL)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(console_handler)
        
        # Avoid propagating to root logger
        logger.propagate = False
        
    return logger
