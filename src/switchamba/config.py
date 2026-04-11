"""Configuration management for Switchamba.

Loads settings from:
1. YAML config file (~/.config/switchamba/config.yaml)
2. Environment variables
3. .env file for Bedrock credentials
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "switchamba"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_ENV_FILE = Path.home() / "SecondLayer" / "deployment" / ".env.prod"


@dataclass
class BedrockConfig:
    """AWS Bedrock configuration."""
    enabled: bool = True
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "eu-central-1"
    model_quick: str = ""
    model_standard: str = ""
    model_deep: str = ""
    timeout_ms: int = 500
    cache_size: int = 256


@dataclass
class DetectionConfig:
    """Language detection configuration."""
    buffer_size: int = 8
    min_chars: int = 3
    score_threshold: float = 0.3
    ngram_weight: float = 0.7
    dict_weight: float = 0.3


@dataclass
class SwitchingConfig:
    """Layout switching configuration."""
    layout_indices: dict[str, int] = field(default_factory=lambda: {
        "en": 0, "ru": 1, "ua": 2,
    })
    debounce_ms: int = 300


@dataclass
class Config:
    """Top-level configuration."""
    device_path: str | None = None  # Auto-detect if None
    log_level: str = "DEBUG"
    bedrock: BedrockConfig = field(default_factory=BedrockConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    switching: SwitchingConfig = field(default_factory=SwitchingConfig)


def load_config(
    config_path: Path | None = None,
    env_path: Path | None = None,
) -> Config:
    """Load configuration from files and environment."""
    config = Config()

    # Load .env for Bedrock credentials
    env_file = env_path or DEFAULT_ENV_FILE
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("Loaded env from %s", env_file)

    # Bedrock config from environment
    config.bedrock.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
    config.bedrock.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    config.bedrock.aws_region = os.getenv("AWS_REGION", "eu-central-1")
    config.bedrock.model_quick = os.getenv("BEDROCK_MODEL_QUICK", "")
    config.bedrock.model_standard = os.getenv("BEDROCK_MODEL_STANDARD", "")
    config.bedrock.model_deep = os.getenv("BEDROCK_MODEL_DEEP", "")

    if not config.bedrock.model_quick:
        config.bedrock.enabled = False
        logger.info("Bedrock disabled (no BEDROCK_MODEL_QUICK)")

    # YAML config override
    yaml_path = config_path or DEFAULT_CONFIG_FILE
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}

            if "device_path" in data:
                config.device_path = data["device_path"]
            if "log_level" in data:
                config.log_level = data["log_level"]

            if "detection" in data:
                det = data["detection"]
                if "buffer_size" in det:
                    config.detection.buffer_size = det["buffer_size"]
                if "min_chars" in det:
                    config.detection.min_chars = det["min_chars"]
                if "score_threshold" in det:
                    config.detection.score_threshold = det["score_threshold"]

            if "switching" in data:
                sw = data["switching"]
                if "layout_indices" in sw:
                    config.switching.layout_indices = sw["layout_indices"]
                if "debounce_ms" in sw:
                    config.switching.debounce_ms = sw["debounce_ms"]

            if "bedrock" in data:
                br = data["bedrock"]
                if "enabled" in br:
                    config.bedrock.enabled = br["enabled"]
                if "timeout_ms" in br:
                    config.bedrock.timeout_ms = br["timeout_ms"]

            logger.info("Loaded config from %s", yaml_path)
        except Exception as e:
            logger.warning("Could not load config: %s", e)

    return config
