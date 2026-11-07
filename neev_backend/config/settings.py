# -*- coding: utf-8 -*-
"""
Configuration and Environment Settings for Neev Backend.
Adheres to Single Responsibility Principle (SRP) for configuration management.
"""

import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
FRONTEND_DIR = BASE_DIR / "frontend"
CUTOFFS_DIR = BASE_DIR / "cutoffs"
VECTOR_INDEX_DIR = BASE_DIR / "vector_index" / "chroma_index"
DEFAULT_SQLITE_PATH = BASE_DIR / "ai_con_app.db"

class Settings:
    """Application settings and runtime environment parameters."""
    
    APP_NAME: str = "Neev AI College & Career Foundation"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    
    # Security & Cryptographic Tokens
    # 256-bit cryptographic secret provided for JWT signatures
    JWT_SECRET: str = os.environ.get(
        "JWT_SECRET", 
        "b3d7b3cf3b8f381781348558daf5648a742907ffa1e2852e848040f444efe71e"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = int(os.environ.get("JWT_EXPIRATION_DAYS", "7"))
    
    # Database Configuration
    DATABASE_URL: Optional[str] = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    SQLITE_PATH: Path = Path(os.environ.get("SQLITE_PATH", str(DEFAULT_SQLITE_PATH)))
    
    # Directory paths
    ROOT_PATH: Path = BASE_DIR
    FRONTEND_PATH: Path = FRONTEND_DIR
    CUTOFFS_PATH: Path = CUTOFFS_DIR
    VECTOR_INDEX_PATH: Path = VECTOR_INDEX_DIR

settings = Settings()
