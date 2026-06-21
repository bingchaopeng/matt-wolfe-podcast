"""Configuration loader for multi-channel podcast project."""
import os
import re
import unicodedata
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
    def tts_style(self) -> str: return self._data.get("tts_style", "lively")
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
        return self._data.get("tts", {}).get("engine", "cosyvoice")

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


# ── MP3 文件名生成规则 ──────────────────────────────────

# 文件名中需移除的非法字符（Windows + URL safe）
_FILENAME_BLACKLIST = re.compile(r'[<>:"/\\|?*%\x00-\x1f]')
# 多个连续空白/分隔符折叠
_MULTI_DASH = re.compile(r'-{2,}')
# 中文字符范围
_CJK = re.compile(r'[一-鿿㐀-䶿豈-﫿]')


def _to_camel_case(segments: list[str]) -> str:
    """将英文词段列表转为驼峰格式，中文段保持原样。

    规则：
    - 第一个英文词：全小写
    - 后续英文词：首字母大写
    - 含中文的段：保持原样
    - 全数字/缩写（AI/GPT等）：首字母大写其余小写

    例：
        ['how', 'florence', 'afforded', 'the', 'renaissance']
        → 'howFlorenceAffordedTheRenaissance'

        ['AI', '新闻', '疯狂的', '一周', '重要内容']
        → 'AI新闻疯狂的一周重要内容'
    """
    result = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        # 含中文 → 直接拼接
        if _CJK.search(seg):
            result.append(seg)
        else:
            # 全大写缩写（AI/GPT/API/LLM 等）→ 保持原样
            if seg.isupper() and len(seg) <= 6:
                result.append(seg)
                continue
            lower = seg.lower()
            has_chinese_before = any(_CJK.search(s) for s in result)
            is_first_english = not result or (i > 0 and not result)
            # 中文后的第一个英文词 → 首字母大写；否则按位置
            if has_chinese_before or (result and result[-1] and not _CJK.search(result[-1])):
                result.append(lower[0].upper() + lower[1:] if lower else "")
            else:
                result.append(lower)
    return "".join(result)


def _fmt_ts(timestamp: str) -> str:
    """从 ISO 时间戳提取 HHMMSS。"""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%H%M%S")
    except (ValueError, TypeError):
        from datetime import datetime as dt2
        return dt2.now().strftime("%H%M%S")


def make_episode_filename(
    title: str,
    video_id: str,
    channel_name: str = "",
    chinese_title: str = "",
    timestamp: str = "",
    max_len: int = 80,
) -> str:
    """
    根据视频标题生成有意义的 MP3 文件名。

    规则：
    1. 有中文标题时使用中文 + 驼峰英文（专有名词保持 CamelCase）
    2. 无中文标题时英文词转为驼峰格式
    3. 分隔符统一用 _（仅用于 前缀/标题/时间戳 之间）
    4. 尾部追加时分秒时间戳

    例：
        title="How Florence Afforded the Renaissance"
        channel="Dwarkesh Patel"
        timestamp="2026-06-20T20:11:46"
        → "dwarkesh_howFlorenceAffordedTheRenaissance_201146.mp3"

        title="AI News: An INSANE Week… Here's What Matters"
        chinese_title="AI 新闻 疯狂的一周 重要内容"
        channel="Matt Wolfe"
        timestamp="2026-06-20T21:15:30"
        → "matt_AI新闻疯狂的一周重要内容_211530.mp3"
    """
    # 时间戳后缀（取时分秒）
    ts = _fmt_ts(timestamp) if timestamp else video_id[-6:] if len(video_id) >= 6 else video_id

    if chinese_title and chinese_title != title:
        name = chinese_title.strip()
        name = _FILENAME_BLACKLIST.sub("", name)
        # 去掉残存标点
        name = re.sub(r"[!?@#$%^&*()…—–\-'\"「」【】『』《》，。、；：？！ -⁯]", "", name)
        # 按空白分割后驼峰化（中文段保持原样，英文段驼峰）
        segments = re.split(r"\s+", name)
        name = _to_camel_case([s for s in segments if s])
    else:
        slug = title.replace("&", "and").replace("@", "at")
        slug = unicodedata.normalize("NFKD", slug).encode("ascii", "ignore").decode("ascii")
        slug = _FILENAME_BLACKLIST.sub("", slug)
        slug = re.sub(r"[,_;:.!'\"(){}\[\]—–-]+", " ", slug)
        slug = re.sub(r"\s+", " ", slug).strip().lower()
        segments = slug.split(" ")
        name = _to_camel_case(segments)

    # 前置频道名简写
    prefix = ""
    if channel_name:
        short = channel_name.replace("'s", "").replace("'", "")
        prefix = short.split()[0].lower() + "_"

    base = f"{prefix}{name}"
    max_base = max_len - len(ts) - 5  # 5 = _ + .mp3
    if len(base) > max_base and max_base > 20:
        base = base[:max_base]

    return f"{base}_{ts}.mp3"


def rename_episode_file(
    old_path: str,
    new_name: str,
) -> str:
    """重命名音频文件，返回新路径。若目标已存在则直接返回。"""
    parent = os.path.dirname(old_path)
    new_path = os.path.join(parent, new_name)
    if old_path == new_path:
        return new_path
    if os.path.isfile(new_path):
        return new_path
    os.rename(old_path, new_path)
    return new_path
