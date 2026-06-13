"""
YouTube 视频获取模块 —— Matt Wolfe 中文播客项目

提供从 YouTube 频道获取视频列表、下载字幕/音频、提取文本等完整功能。
"""

import json
import logging
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

# ── 模块级缓存 ──────────────────────────────────────────────
_channel_id_cache: dict[str, str] = {}

# ── 公开函数 ────────────────────────────────────────────────


def resolve_channel_id(channel_url: str) -> Optional[str]:
    """从 YouTube 频道 URL 中提取 channel_id。

    通过抓取频道页面 HTML，用正则匹配 ``channel_id`` 或 ``externalId``。

    Args:
        channel_url: YouTube 频道 URL，例如 ``https://www.youtube.com/@mattwolfe``。

    Returns:
        频道 ID 字符串，若无法解析则返回 None。
    """
    if channel_url in _channel_id_cache:
        return _channel_id_cache[channel_url]

    logger.info("正在解析频道 ID: %s", channel_url)
    try:
        req = Request(
            channel_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # 尝试多种正则模式
        patterns = [
            r'"channelId"\s*:\s*"([^"]+)"',
            r'"externalId"\s*:\s*"([^"]+)"',
            r'"browseId"\s*:\s*"([^"]+)"',
            r'channel_id=([^"&?]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                cid = match.group(1)
                _channel_id_cache[channel_url] = cid
                logger.info("解析到频道 ID: %s", cid)
                return cid

        logger.warning("未能从页面中解析出 channel_id: %s", channel_url)
        return None

    except (HTTPError, URLError, OSError) as exc:
        logger.warning("请求频道页面失败 (%s): %s", channel_url, exc)
        return None


def get_channel_videos(
    channel_url: str, max_results: int = 5
) -> list[dict]:
    """获取指定 YouTube 频道的最新视频列表。

    内部通过 ``resolve_channel_id`` 解析频道 ID，然后读取 YouTube 官方 RSS feed。

    Args:
        channel_url: 频道 URL。
        max_results:  返回的最大视频数量，默认 5。

    Returns:
        ``[{id, title, published, updated, link, url}, ...]`` 格式的列表。
        失败时返回空列表并记录警告日志。
    """
    channel_id = resolve_channel_id(channel_url)
    if not channel_id:
        logger.warning("无法获取频道 ID，跳过视频列表获取: %s", channel_url)
        return []

    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    logger.info("正在获取 RSS feed: %s", feed_url)

    try:
        req = Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            xml_bytes = resp.read()
    except (HTTPError, URLError, OSError) as exc:
        logger.warning("获取 RSS feed 失败: %s", exc)
        return []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("解析 RSS XML 失败: %s", exc)
        return []

    # RSS 命名空间
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    videos: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        if len(videos) >= max_results:
            break

        video_id = _extract_video_id(entry, ns)
        if not video_id:
            continue

        title_el = entry.find("atom:title", ns)
        published_el = entry.find("atom:published", ns)
        updated_el = entry.find("atom:updated", ns)
        link_el = entry.find("atom:link", ns)

        videos.append({
            "id": video_id,
            "title": title_el.text if title_el is not None else "",
            "published": published_el.text if published_el is not None else "",
            "updated": updated_el.text if updated_el is not None else "",
            "link": link_el.attrib.get("href", f"https://www.youtube.com/watch?v={video_id}") if link_el is not None else f"https://www.youtube.com/watch?v={video_id}",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    logger.info("获取到 %d 个视频", len(videos))
    return videos


def download_subtitles(video_url: str, output_dir: str) -> Optional[str]:
    """使用 yt-dlp 下载 YouTube 自动生成英文字幕。

    命令等价于::

        yt-dlp --write-auto-subs --write-subs --sub-langs en \\
               --skip-download --convert-subs srt \\
               --output "{output_dir}/%(id)s" {video_url}

    Args:
        video_url:   YouTube 视频 URL。
        output_dir:  字幕文件输出目录。

    Returns:
        下载成功的 SRT 文件绝对路径，若失败或无字幕则返回 None。
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s")

    cmd = [
        "yt-dlp",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs", "en",
        "--skip-download",
        "--convert-subs", "srt",
        "--output", out_template,
        "--no-progress",
        video_url,
    ]

    logger.info("下载字幕: %s", video_url)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.warning(
                "yt-dlp 字幕下载失败 (return code %d): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return None

        # 从输出中找到 SRT 文件路径
        return _find_srt_file(output_dir, video_url)

    except subprocess.TimeoutExpired:
        logger.warning("字幕下载超时: %s", video_url)
        return None
    except FileNotFoundError:
        logger.error("未找到 yt-dlp，请确认已安装 (pip install yt-dlp)")
        return None
    except OSError as exc:
        logger.warning("字幕下载异常: %s", exc)
        return None


def extract_text_from_srt(srt_path: str) -> str:
    """从 SRT 字幕文件中提取纯文本。

    丢弃序号和时间轴行，仅保留字幕文本内容。段落之间用空行分隔。

    Args:
        srt_path: SRT 文件路径。

    Returns:
        清洗后的纯文字字符串。出错时返回空字符串。
    """
    if not srt_path or not os.path.isfile(srt_path):
        logger.warning("SRT 文件不存在: %s", srt_path)
        return ""

    try:
        with open(srt_path, encoding="utf-8") as fh:
            content = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        # 部分 SRT 为 UTF-16，尝试回退
        try:
            with open(srt_path, encoding="utf-16") as fh:
                content = fh.read()
        except (OSError, UnicodeDecodeError) as exc2:
            logger.warning("读取 SRT 文件失败: %s / %s", exc, exc2)
            return ""

    lines = content.splitlines()
    text_parts: list[str] = []
    paragraph: list[str] = []

    # 正则：序号行（纯数字）或时间轴行（数字:数字:数字）
    seq_re = re.compile(r"^\d+$")
    time_re = re.compile(r"^\d{1,2}:\d{2}:\d{2}")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 空行 = 段落结束
            if paragraph:
                text_parts.append(" ".join(paragraph))
                paragraph = []
            continue
        if seq_re.match(stripped):
            continue
        if time_re.match(stripped):
            continue
        # 去除常见的 SRT 标签
        clean = re.sub(r"<[^>]+>", "", stripped)
        # 去除全大写音效标注 e.g. [MUSIC], (APPLAUSE)
        clean = re.sub(r"[\[\(][A-Z\s]+[\]\)]", "", clean).strip()
        if clean:
            paragraph.append(clean)

    if paragraph:
        text_parts.append(" ".join(paragraph))

    return "\n\n".join(text_parts)


def get_transcript_direct(video_url: str, output_dir: str) -> Optional[str]:
    """直接获取视频字幕文本。

    优先尝试通过 yt-dlp 检查是否有内嵌字幕；若有则直接下载并提取文本，
    否则返回 None 以供外部使用 Whisper 等其他方式转录。

    Args:
        video_url:  YouTube 视频 URL。
        output_dir: 临时文件目录。

    Returns:
        字幕文本字符串，若无法获取则返回 None。
    """
    srt_path = download_subtitles(video_url, output_dir)
    if srt_path:
        text = extract_text_from_srt(srt_path)
        if text:
            logger.info("成功获取字幕文本 (%d 字符)", len(text))
            return text
        logger.warning("字幕文件为空: %s", srt_path)
    else:
        logger.info("视频无可用字幕，将使用音频转录回退: %s", video_url)

    return None


def download_audio(video_url: str, output_dir: str) -> Optional[str]:
    """下载 YouTube 视频的音频（MP3 格式）。

    当字幕不可用时，以此作为 Whisper 转录的备选方案。

    命令等价于::

        yt-dlp -x --audio-format mp3 --output "{output_dir}/%(id)s.%(ext)s" {video_url}

    Args:
        video_url:  YouTube 视频 URL。
        output_dir: 音频文件输出目录。

    Returns:
        下载的 MP3 文件绝对路径，失败时返回 None。
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--output", out_template,
        "--no-progress",
        video_url,
    ]

    logger.info("下载音频: %s", video_url)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.warning(
                "yt-dlp 音频下载失败 (return code %d): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return None

        # 从输出中匹配最终文件名
        return _find_audio_file(output_dir, video_url)

    except subprocess.TimeoutExpired:
        logger.warning("音频下载超时: %s", video_url)
        return None
    except FileNotFoundError:
        logger.error("未找到 yt-dlp，请确认已安装 (pip install yt-dlp)")
        return None
    except OSError as exc:
        logger.warning("音频下载异常: %s", exc)
        return None


# ── ProcessedTracker ────────────────────────────────────────

class ProcessedTracker:
    """基于 JSON 文件的已处理视频追踪器。

    将已处理视频的 ID 及元数据持久化至本地 JSON 文件，
    提供简单的去重判断能力。使用文件锁机制保证多线程安全。
    """

    _lock = threading.Lock()

    def __init__(self, json_path: Optional[str] = None) -> None:
        """初始化追踪器。

        Args:
            json_path: JSON 存储路径。默认为
                ``C:\\Users\\30777\\matt-wolfe-podcast\\data\\processed_videos.json``。
        """
        if json_path is None:
            json_path = os.path.join(
                "C:\\Users\\30777\\matt-wolfe-podcast", "data", "processed_videos.json"
            )
        self._json_path = json_path
        self._data: dict[str, dict] = {}
        self._load()

    # ── 公开方法 ──

    def is_processed(self, video_id: str) -> bool:
        """检查视频是否已被处理。

        Args:
            video_id: YouTube 视频 ID。

        Returns:
            若视频已被记录则返回 True。
        """
        with self._lock:
            self._load()
            return video_id in self._data

    def mark_processed(
        self, video_id: str, metadata: dict
    ) -> None:
        """将视频标记为已处理。

        Args:
            video_id:  YouTube 视频 ID。
            metadata:  附加元数据，至少应包含 ``title`` 字段。
                       ``processed_at`` 会自动填充当前 UTC 时间。
                       ``status`` 默认设为 ``"completed"``。
        """
        with self._lock:
            self._load()
            record = dict(metadata)
            record.setdefault("processed_at", datetime.now(timezone.utc).isoformat())
            record.setdefault("status", "completed")
            self._data[video_id] = record
            self._save()

    def get_all_processed(self) -> dict:
        """获取所有已处理视频的字典。

        Returns:
            ``{video_id: metadata_dict, ...}``。
        """
        with self._lock:
            self._load()
            return dict(self._data)

    def get_unprocessed(self, videos: list[dict]) -> list[dict]:
        """从视频列表中过滤出尚未处理的视频。

        Args:
            videos: 视频字典列表，每个字典需包含 ``id`` 键。

        Returns:
            未处理过的视频列表。
        """
        with self._lock:
            self._load()
            return [v for v in videos if v.get("id") not in self._data]

    def get_count(self) -> int:
        """返回已处理视频的总数。

        Returns:
            已处理视频数量。
        """
        with self._lock:
            self._load()
            return len(self._data)

    # ── 内部方法 ──

    def _load(self) -> None:
        """从 JSON 文件加载数据。"""
        try:
            if os.path.isfile(self._json_path):
                with open(self._json_path, encoding="utf-8") as fh:
                    self._data = json.load(fh)
            else:
                self._data = {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取追踪文件失败 (%s)，使用空数据: %s", self._json_path, exc)
            self._data = {}

    def _save(self) -> None:
        """将数据写入 JSON 文件。"""
        os.makedirs(os.path.dirname(self._json_path), exist_ok=True)
        tmp_path = self._json_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._json_path)
        except OSError as exc:
            logger.warning("写入追踪文件失败: %s", exc)


# ── 内部辅助函数 ──────────────────────────────────────────


def _extract_video_id(entry: ET.Element, ns: dict) -> Optional[str]:
    """从 RSS entry 元素中提取视频 ID。"""
    # 标准 videoId 方式
    vid_el = entry.find("yt:videoId", {"yt": "http://www.youtube.com/xml/schemas/2015"})
    if vid_el is not None and vid_el.text:
        return vid_el.text

    # 从链接中解析
    link_el = entry.find("atom:link", ns)
    if link_el is not None:
        href = link_el.attrib.get("href", "")
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]

    return None


def _find_srt_file(output_dir: str, video_url: str) -> Optional[str]:
    """从输出目录中找到最近生成的 SRT 文件。

    先尝试解析视频 ID 精确匹配，否则取目录下最新的 .srt / .en.srt 文件。
    """
    # 尝试从 URL 解析 video_id
    parsed = urlparse(video_url)
    vid = parse_qs(parsed.query).get("v", [None])[0]
    if vid:
        # 精确匹配
        candidates = [
            os.path.join(output_dir, f"{vid}.srt"),
            os.path.join(output_dir, f"{vid}.en.srt"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                logger.info("找到字幕文件: %s", path)
                return os.path.abspath(path)

    # 兜底：取最新 .srt 文件
    srt_files = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".srt") and os.path.isfile(os.path.join(output_dir, f))
    ]
    if srt_files:
        latest = max(srt_files, key=os.path.getmtime)
        logger.info("找到字幕文件（兜底）: %s", latest)
        return os.path.abspath(latest)

    logger.warning("未找到字幕文件: %s", video_url)
    return None


def _find_audio_file(output_dir: str, video_url: str) -> Optional[str]:
    """从输出目录中找到下载的 MP3 文件。"""
    parsed = urlparse(video_url)
    vid = parse_qs(parsed.query).get("v", [None])[0]
    if vid:
        path = os.path.join(output_dir, f"{vid}.mp3")
        if os.path.isfile(path):
            logger.info("找到音频文件: %s", path)
            return os.path.abspath(path)

    # 兜底：取最新 .mp3 文件
    mp3_files = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".mp3") and os.path.isfile(os.path.join(output_dir, f))
    ]
    if mp3_files:
        latest = max(mp3_files, key=os.path.getmtime)
        logger.info("找到音频文件（兜底）: %s", latest)
        return os.path.abspath(latest)

    logger.warning("未找到音频文件: %s", video_url)
    return None


# ── 测试入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    videos = get_channel_videos("https://www.youtube.com/@mattwolfe", max_results=3)
    print(json.dumps(videos, indent=2, ensure_ascii=False))
