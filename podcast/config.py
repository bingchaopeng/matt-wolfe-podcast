"""Configuration loader for multi-channel podcast project."""
import os
import yaml
from pathlib import Path
from typing import Any


class ChannelConfig:
    """Configuration for a single channel."""

    def __init__(self, data: dict, root: "Config"):
        self._data = data
        self._root = root

    @property
    def name(self) -> str: return self._data.get("name", "")
    @property
    def youtube_url(self) -> str: return self._data.get("youtube_url", "")
    @property
    def channel_id(self) -> str: return self._data.get("channel_id", "")
    @property
    def tts_voice(self) -> str: return self._data.get("tts_voice", "zh-CN-XiaoxiaoNeural")
    @property
    def podcast_title(self) -> str: return self._data.get("podcast_title", "")
    @property
    def podcast_description(self) -> str: return self._data.get("podcast_description", "")
    @property
    def podcast_author(self) -> str: return self._data.get("podcast_author", "AI 播客工坊")
    @property
    def feed_filename(self) -> str: return self._data.get("feed_filename", "feed.xml")
    @property
    def feed_path(self) -> str:
        return str(self._root.project_root / self._root._data.get("podcast", {}).get("output_dir", "./public") / self.feed_filename)

    def __repr__(self) -> str:
        return f"<Channel: {self.name}>"


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
        config_path = self._find_config()
        self.project_root = Path(config_path).parent
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        self._load_env()
        # Build channel configs
        self._channels: list[ChannelConfig] = [
            ChannelConfig(c, self) for c in self._data.get("channels", [])
        ]

    def _find_config(self) -> str:
        ROOT = Path(__file__).parent.parent
        return str(ROOT / "config.yaml")

    def _load_env(self):
        root = Path(self._find_config()).parent
        env_path = root / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ.setdefault(key.strip(), val.strip())

    # ── Channels ──
    @property
    def channels(self) -> list[ChannelConfig]:
        return self._channels

    def get_channel(self, name: str) -> ChannelConfig | None:
        for c in self._channels:
            if c.name == name:
                return c
        return None

    # ── Legacy single-channel properties (backward compat) ──
    @property
    def channel_name(self) -> str:
        return self._channels[0].name if self._channels else ""

    @property
    def channel_url(self) -> str:
        return self._channels[0].youtube_url if self._channels else ""

    @property
    def channel_id(self) -> str:
        return self._channels[0].channel_id if self._channels else ""

    @property
    def tts_voice(self) -> str:
        return self._channels[0].tts_voice if self._channels else "zh-CN-XiaoxiaoNeural"

    @property
    def proxy(self) -> str:
        return self._data.get("network", {}).get("proxy", "")

    # ── LLM ──
    @property
    def llm_model(self) -> str:
        return self._data.get("llm", {}).get("model", "deepseek-v4-flash")

    @property
    def llm_base_url(self) -> str:
        return self._data.get("llm", {}).get("anthropic_base_url",
                                              "https://api.deepseek.com/anthropic")

    @property
    def llm_max_tokens(self) -> int:
        return self._data.get("llm", {}).get("max_tokens", 4096)

    @property
    def llm_temperature(self) -> float:
        return self._data.get("llm", {}).get("temperature", 0.3)

    # ── TTS ──
    @property
    def tts_engine(self) -> str:
        return self._data.get("tts", {}).get("engine", "edge-tts")

    @property
    def tts_rate(self) -> str:
        return self._data.get("tts", {}).get("rate", "+0%")

    @property
    def tts_volume(self) -> str:
        return self._data.get("tts", {}).get("volume", "+0%")

    # ── Podcast ──
    @property
    def podcast_language(self) -> str:
        return self._data.get("podcast", {}).get("language", "zh-CN")

    @property
    def podcast_output_dir(self) -> str:
        return str(self.project_root / self._data.get("podcast", {}).get("output_dir", "./public"))

    @property
    def podcast_episodes_dir(self) -> str:
        return str(self.project_root / self._data.get("podcast", {}).get("episodes_dir", "./data/episodes"))

    @property
    def podcast_website(self) -> str:
        return self._data.get("podcast", {}).get("website", "")

    @property
    def max_episodes_per_run(self) -> int:
        return self._data.get("schedule", {}).get("max_episodes_per_run", 1)

    @property
    def daily_time(self) -> str:
        return self._data.get("schedule", {}).get("daily_time", "21:00")


config = Config()

def get_config() -> Config:
    return Config()
