"""
Production-ready configuration manager for Evolution Ecosystem.
FIXED VERSION of failed 'CURIOSITY: PROJECT: PRIMING PUMP' mission.

Architectural Decisions:
1. Lazy loading with caching to prevent repeated environment validation
2. Comprehensive error recovery with fallback configurations
3. Type-safe configuration objects with Pydantic validation
4. Environment variable coercion with sensible defaults
5. Firebase Admin SDK integration for ecosystem persistence
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field, validator
from functools import lru_cache
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AssetType(str, Enum):
    """Supported asset types for fragmentation."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    MULTIMODAL = "multimodal"


class FragmentationStrategy(str, Enum):
    """Strategies for content fragmentation."""
    SEMANTIC_CHUNKS = "semantic_chunks"
    FIXED_SIZE = "fixed_size"
    SENTENCE_BOUNDARY = "sentence_boundary"
    PARAGRAPH = "paragraph"
    TOPIC_SEGMENTATION = "topic_segmentation"


@dataclass
class FragmentationConfig:
    """Configuration for content fragmentation."""
    asset_type: AssetType
    strategy: FragmentationStrategy
    min_fragment_size: int = 100
    max_fragment_size: int = 10000
    overlap_percentage: float = 0.1
    quality_threshold: float = 0.8


class MarketplaceConfig(BaseModel):
    """Marketplace configuration with validation."""
    base_url: str = Field(default="https://api.marketplace.evolution.eco")
    api_key: Optional[str] = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    enable_analytics: bool = Field(default=True)
    
    @validator('base_url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('base_url must start with http:// or https://')
        return v


class FirebaseConfig(BaseModel):
    """Firebase configuration with validation and safety."""
    project_id: str
    private_key_id: Optional[str] = None
    private_key: Optional[str] = None
    client_email: Optional[str] = None
    client_id: Optional[str] = None
    client_cert_url: Optional[str] = None
    use_emulator: bool = Field(default=False)
    emulator_host: str = Field(default="localhost")
    emulator_port: int = Field(default=8080)
    
    class Config:
        validate_assignment = True


class ConfigManager:
    """Centralized configuration management with validation and error recovery."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger(f"{__name__}.ConfigManager")
            self._firebase_app = None
            self._firestore_client = None
            self._config_cache = {}
            self._load_configuration()
            self._initialized = True
    
    def _load_configuration(self) -> None:
        """Load and validate all configurations."""
        try:
            self._validate_environment()
            self.logger.info("Environment validation successful")
            
            # Initialize Firebase if credentials available
            self._initialize_firebase()
            
            # Load configurations
            self._load_fragmentation_config()
            self._load_marketplace_config()
            
            self.logger.info("All configurations loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Configuration loading failed: {str(e)}")
            self._load_fallback_configurations()
    
    def _validate_environment(self) -> None:
        """Validate required environment variables with detailed error reporting."""
        required_vars = [
            'FIREBASE_PROJECT_ID',
            'FIREBASE_PRIVATE_KEY_ID',
            'FIREBASE_PRIVATE_KEY',
            'FIREBASE_CLIENT_EMAIL',
            'FIREBASE_CLIENT_ID',
        ]
        
        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value or value.strip() == '':