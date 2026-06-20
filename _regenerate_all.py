"""
批量重生成脚本：用 CosyVoice 2 重新生成所有现有音频。

处理流程：
1. 遍历 processed_videos.json 中所有有字幕文件的条目
2. 提取字幕文本 → DeepSeek 翻译生成中文播客脚本 → CosyVoice 2 生成音频
3. 更新 audio_file 指向新文件（同路径同名，仅替换内容）

注意：
- 每集生成 15-21x RTF，预计总耗时 ~40+ 小时
- 脚本运行期间 GPU 100% 占用
- 每集单独处理，可随时中断后 resume（检查已存在的脚本文件）

用法：
    python _regenerate_all.py [--start-from VIDEO_ID] [--single VIDEO_ID]
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("_regenerate_all.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("regenerate")

# 确保项目路径
PROJECT_ROOT = Path(__file__).parent
os.chdir(str(PROJECT_ROOT))

# ── 加载项目模块 ──────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "cosyvoice-src"))
sys.path.insert(0, str(PROJECT_ROOT / "cosyvoice-src" / "third_party" / "Matcha-TTS"))

from podcast.fetcher import extract_text_from_srt, ProcessedTracker
from podcast.translator import get_podcast_script, translate_title
from podcast.config import make_episode_filename
from podcast.voice_cloner import get_voice_cloner

# ── 频道风格映射 ──
CHANNEL_STYLES = {
    "Matt Wolfe": "lively",
    "Lenny's Podcast": "relaxed",
    "Dwarkesh Patel": "serious",
    "Andrej Karpathy": "serious",
}

# ── 脚本缓存目录 ──
SCRIPT_CACHE_DIR = PROJECT_ROOT / "data" / "podcast_scripts"
SCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cached_script(video_id: str, title: str, description: str,
                       transcript: str, channel: str, host_style_desc: str) -> str:
    """获取播客脚本（优先从缓存读取，否则调用 DeepSeek API）。

    Args:
        host_style_desc: 播主风格文字描述，如 "Matt Wolfe 的风格是热情、易懂、有见解"
    """
    cache_path = SCRIPT_CACHE_DIR / f"{video_id}.txt"

    if cache_path.exists():
        logger.info("  Using cached script for %s", video_id)
        return cache_path.read_text(encoding="utf-8")

    logger.info("  Translating via DeepSeek: %s (%d chars)", title, len(transcript))
    # 长文本增大 max_tokens
    est_output_tokens = max(8192, len(transcript) // 4)
    script = get_podcast_script(
        title, description, transcript,
        host_name=channel,
        host_style=host_style_desc,
        max_tokens=min(est_output_tokens, 32000),
    )

    # 缓存脚本
    cache_path.write_text(script, encoding="utf-8")
    logger.info("  Script cached: %s (%d chars)", cache_path.name, len(script))
    return script


def regenerate_episode(video_id: str, ep: dict) -> dict:
    """
    重新生成单个 episode 的音频。

    Returns:
        {"status": "ok"|"skip"|"error", "reason": str, "duration": s}
    """
    channel = ep.get("channel", "")
    title = ep.get("title", "")
    audio_file = ep.get("audio_file", "")
    url = ep.get("url", "")

    if not channel:
        return {"status": "skip", "reason": "No channel info"}

    # 确定风格
    style = CHANNEL_STYLES.get(channel, "lively")
    host_style = {
        "Matt Wolfe": "Matt Wolfe 的风格是热情、易懂、有见解",
        "Lenny's Podcast": "Lenny 的风格是深度、好奇、善于引导嘉宾分享见解",
        "Dwarkesh Patel": "Dwarkesh Patel 的风格是理性、深入、关注 AI 前沿趋势",
        "Andrej Karpathy": "Andrej Karpathy 的风格是技术深度强、逻辑清晰、善于用通俗例子解释复杂概念",
    }.get(channel, "风格热情、易懂、有见解")

    # 查找字幕文件
    srt_path = PROJECT_ROOT / "data" / "episodes" / f"{video_id}.en.srt"
    if not srt_path.exists():
        # 也可能是文章类（无字幕）
        return {"status": "skip", "reason": f"No SRT file: {srt_path.name}"}

    try:
        # 1. 提取字幕
        transcript = extract_text_from_srt(str(srt_path))
        if not transcript:
            return {"status": "skip", "reason": "Empty transcript"}

        # 2. 翻译脚本
        script = get_cached_script(video_id, title, "", transcript, channel, host_style)
        if not script:
            return {"status": "error", "reason": "Empty script from DeepSeek"}

        # 3. 生成音频
        output_path = str(PROJECT_ROOT / "data" / "episodes" / audio_file)
        logger.info("  Generating audio: %s (%d chars, %s style)",
                     audio_file, len(script), style)

        cloner = get_voice_cloner()
        result = cloner.generate_tts(
            script, output_path,
            person_name=channel,
            style_override=style,
        )

        duration = result.get("duration_seconds", 0)
        logger.info("  Audio generated: %.1fs", duration)

        return {
            "status": "ok",
            "duration": duration,
            "script_chars": len(script),
            "audio_file": audio_file,
        }

    except Exception as e:
        logger.error("  Error regenerating %s: %s", video_id, e, exc_info=True)
        return {"status": "error", "reason": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Regenerate all audio with CosyVoice 2")
    parser.add_argument("--start-from", help="Video ID to start from (skip earlier)")
    parser.add_argument("--single", help="Only process this video ID")
    parser.add_argument("--force", action="store_true", help="Regenerate even if script cached")
    args = parser.parse_args()

    # 加载已处理列表
    tracker = ProcessedTracker()
    all_episodes = tracker.get_all_processed()

    logger.info("Loaded %d processed episodes", len(all_episodes))

    # 排序：有字幕的排前面，按时长升序
    episodes = []
    for vid, ep in all_episodes.items():
        srt_path = PROJECT_ROOT / "data" / "episodes" / f"{vid}.en.srt"
        has_srt = srt_path.exists()
        duration = ep.get("duration_seconds", 999999)
        episodes.append((vid, ep, has_srt, duration))

    # 排序：有字幕的优先，然后按时长升序
    episodes.sort(key=lambda x: (not x[2], x[3]))

    # 过滤
    if args.single:
        episodes = [e for e in episodes if e[0] == args.single]
    elif args.start_from:
        started = False
        filtered = []
        for e in episodes:
            if e[0] == args.start_from:
                started = True
            if started:
                filtered.append(e)
        episodes = filtered

    # 统计
    total = len(episodes)
    with_srt = sum(1 for _, _, has_srt, _ in episodes if has_srt)
    without_srt = sum(1 for _, _, has_srt, _ in episodes if not has_srt)
    logger.info("To process: %d episodes (%d with SRT, %d without SRT)",
                total, with_srt, without_srt)

    results = {"ok": 0, "skip": 0, "error": 0, "total_duration": 0}

    for i, (vid, ep, has_srt, duration) in enumerate(episodes):
        if not has_srt:
            logger.info("[%d/%d] SKIP %s (%s): no SRT", i + 1, total, vid, ep.get("title", ""))
            results["skip"] += 1
            continue

        logger.info("[%d/%d] %s - %s (%ds SRT)", i + 1, total, vid, ep.get("title", ""),
                     os.path.getsize(PROJECT_ROOT / "data" / "episodes" / f"{vid}.en.srt"))

        start = time.time()
        r = regenerate_episode(vid, ep)
        elapsed = time.time() - start

        results[r.get("status", "error")] = results.get(r.get("status", "error"), 0) + 1
        if r.get("status") == "ok":
            results["total_duration"] += r.get("duration", 0)

        logger.info("  -> %s (%s) [%ds elapsed]",
                     r["status"], r.get("reason", ""), elapsed)

        # 写入进度
        stats = {
            "progress": f"{i + 1}/{total}",
            "last": vid,
            "results": results,
            "updated_at": datetime.now().isoformat(),
        }
        with open("_regenerate_progress.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    # 总结
    logger.info("=" * 50)
    logger.info("REGENERATION COMPLETE")
    logger.info("  OK:    %d", results["ok"])
    logger.info("  SKIP:  %d", results["skip"])
    logger.info("  ERROR: %d", results["error"])
    logger.info("  Total audio duration: %.1f min", results["total_duration"] / 60)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
