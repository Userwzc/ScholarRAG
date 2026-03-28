"""API configuration module.

This module re-exports configuration from the central config module.
All environment variable handling is now centralized in config/settings.py.
"""

from config.settings import config

# Re-export for backward compatibility
API_HOST = config.API_HOST
API_PORT = config.API_PORT
API_UPLOAD_DIR = config.API_UPLOAD_DIR
DATABASE_PATH = config.DATABASE_PATH
DATABASE_URL = config.DATABASE_URL
