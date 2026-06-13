"""Configuration loader for Matt Wolfe podcast project."""
import os
import yaml
from pathlib import Path
from typing import Any

class Config:
    """Singleton configuration loaded from config.yaml and .env."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._loaded = True
        self._load()

    def _load(self):
        # Find config.yaml (look in project root)
        config_path = self._find_config()
        with open(config_path, 'r', encoding='utf-8') as f:
            self._data = yaml.safe_load(f)
        # Load .env
        self._load_env()

    def _find_config(self) -> str:
        # Search from current dir up to find config.yaml
        # Fall back to default path: ROOT/config.yaml
        ROOT = Path(__file__).parent.parent
        return str(ROOT / 'config.yaml')

    def _load_env(self):
        """Load .env file if exists."""
        root = Path(self._find_config()).parent
        env_path = root / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, val = line.split('=', 1)
                        os.environ.setdefault(key.strip(), val.strip())

    # Properties for each config section
    @property
    def channel_name(self) -> str: return self._data.get('channel', {}).get('name', '')
    @property
    def channel_url(self) -> str: return self._data.get('channel', {}).get('youtube_url', '')
    @property
    def channel_id(self) -> str: return self._data.get('channel', {}).get('channel_id', '')
    @property
    def llm_model(self) -> str: return self._data.get('llm', {}).get('model', 'deepseek-v4-flash')
    @property
    def llm_base_url(self) -> str: return self._data.get('llm', {}).get('anthropic_base_url', 'https://api.deepseek.com/anthropic')
    @property
    def llm_max_tokens(self) -> int: return self._data.get('llm', {}).get('max_tokens', 4096)
    @property
    def llm_temperature(self) -> float: return self._data.get('llm', {}).get('temperature', 0.3)
    @property
    def tts_voice(self) -> str: return self._data.get('tts', {}).get('voice', 'zh-CN-XiaoxiaoNeural')
    @property
    def tts_rate(self) -> str: return self._data.get('tts', {}).get('rate', '+0%')
    @property
    def podcast_title(self) -> str: return self._data.get('podcast', {}).get('title', '')
    @property
    def podcast_description(self) -> str: return self._data.get('podcast', {}).get('description', '')
    @property
    def podcast_author(self) -> str: return self._data.get('podcast', {}).get('author', '')
    @property
    def podcast_language(self) -> str: return self._data.get('podcast', {}).get('language', 'zh-CN')
    @property
    def podcast_output_dir(self) -> str:
        return str(Path(self._find_config()).parent / self._data.get('podcast', {}).get('output_dir', './public'))
    @property
    def podcast_episodes_dir(self) -> str:
        return str(Path(self._find_config()).parent / self._data.get('podcast', {}).get('episodes_dir', './data/episodes'))
    @property
    def feed_filename(self) -> str: return self._data.get('podcast', {}).get('feed_filename', 'feed.xml')
    @property
    def podcast_website(self) -> str: return self._data.get('podcast', {}).get('website', '')
    @property
    def max_episodes_per_run(self) -> int: return self._data.get('schedule', {}).get('max_episodes_per_run', 1)
    @property
    def daily_time(self) -> str: return self._data.get('schedule', {}).get('daily_time', '21:00')

config = Config()  # module-level singleton

def get_config() -> Config:
    """Get the singleton config instance."""
    return Config()
