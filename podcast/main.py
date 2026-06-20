"""Main orchestrator for multi-channel podcast automation."""
import os
import logging
import shutil
from datetime import datetime
from pathlib import Path

from podcast.config import get_config, ChannelConfig
from podcast.fetcher import get_channel_videos, download_subtitles, extract_text_from_srt, ProcessedTracker
from podcast.translator import get_podcast_script
from podcast.tts import generate_audio_long_text
from podcast.rss import create_feed, add_episode, build_feed_from_history, save_feed

logger = logging.getLogger(__name__)


def ensure_dirs(config):
    """Ensure output and episodes directories exist."""
    os.makedirs(config.podcast_episodes_dir, exist_ok=True)
    os.makedirs(config.podcast_output_dir, exist_ok=True)


def _get_host_style(channel_name: str) -> str:
    """Get the host's speaking style description for the translator prompt."""
    styles = {
        "Matt Wolfe": "Matt Wolfe 的风格是热情、易懂、有见解",
        "Lenny's Podcast": "Lenny 的风格是深度、好奇、善于引导嘉宾分享见解",
        "Dwarkesh Patel": "Dwarkesh Patel 的风格是理性、深入、关注 AI 前沿趋势",
        "Andrej Karpathy": "Andrej Karpathy 的风格是技术深度强、逻辑清晰、善于用通俗例子解释复杂概念",
    }
    return styles.get(channel_name, "风格热情、易懂、有见解")


def process_channel(channel: ChannelConfig, tracker: ProcessedTracker, dry_run: bool = False) -> dict:
    """
    Process a single channel: check for new videos, translate, generate audio, update RSS.

    Args:
        channel: Channel configuration.
        tracker: ProcessedTracker instance (shared across channels).
        dry_run: If True, only check for new videos.

    Returns:
        dict with processing summary.
    """
    config = get_config()
    result = {
        "channel": channel.name,
        "new_videos_found": 0,
        "processed": [],
        "errors": [],
        "skipped": [],
    }

    # Step 1: Get latest videos
    logger.info("[%s] Checking for new videos...", channel.name)
    videos = get_channel_videos(channel.youtube_url, max_results=5, channel_id_override=channel.channel_id)
    if not videos:
        logger.warning("[%s] No videos found", channel.name)
        return result

    # Filter by channel (using channel_id from RSS metadata when available)
    unprocessed = []
    for v in videos:
        v["channel"] = channel.name
        if not tracker.is_processed(v["id"]):
            unprocessed.append(v)

    result["new_videos_found"] = len(unprocessed)
    if not unprocessed:
        logger.info("[%s] No new videos to process", channel.name)
        return result

    # Limit per run
    videos_to_process = unprocessed[:config.max_episodes_per_run]
    logger.info("[%s] Processing %d video(s)", channel.name, len(videos_to_process))

    if dry_run:
        for v in videos_to_process:
            logger.info("[DRY RUN] Would process: %s - %s", channel.name, v["title"])
            result["processed"].append({"id": v["id"], "title": v["title"], "dry_run": True})
        return result

    host_style = _get_host_style(channel.name)

    # Step 2: Process each video
    for video in videos_to_process:
        try:
            video_id = video["id"]
            video_title = video["title"]
            video_url = video.get("url", f"https://www.youtube.com/watch?v={video_id}")

            logger.info("[%s] Processing: %s", channel.name, video_title)

            # Download subtitles
            subs_path = download_subtitles(video_url, config.podcast_episodes_dir)
            if not subs_path or not os.path.exists(subs_path):
                logger.error("[%s] No subtitles for %s", channel.name, video_id)
                result["errors"].append({"id": video_id, "reason": "No subtitles"})
                continue

            # Extract text
            transcript = extract_text_from_srt(subs_path)
            if not transcript:
                logger.error("[%s] Empty transcript for %s", channel.name, video_id)
                result["errors"].append({"id": video_id, "reason": "Empty transcript"})
                continue

            description = video.get("description", "")

            # Translate and create podcast script (channel-aware)
            logger.info("[%s] Translating: %s", channel.name, video_title)
            podcast_script = get_podcast_script(
                video_title, description, transcript,
                host_name=channel.name,
                host_style=host_style,
            )

            # Generate audio with channel-specific voice
            audio_filename = f"{video_id}.mp3"
            audio_path = os.path.join(config.podcast_episodes_dir, audio_filename)

            logger.info("[%s] Generating audio: %s (voice=%s)",
                       channel.name, audio_filename, channel.tts_voice)
            audio_result = generate_audio_long_text(
                podcast_script,
                audio_path,
                voice=channel.tts_voice,
            )

            audio_url = f"{config.podcast_website.rstrip('/')}/episodes/{audio_filename}"
            published = datetime.fromisoformat(video["published"]) if "published" in video else datetime.now()

            episode_desc = f"{channel.name} 最新视频《{video_title}》的中文同音翻译播客版本。"

            # Mark as processed
            tracker.mark_processed(video_id, {
                "title": video_title,
                "channel": channel.name,
                "published": video["published"],
                "processed_at": datetime.now().isoformat(),
                "audio_file": audio_filename,
                "duration_seconds": audio_result.get("duration_seconds", 0),
                "url": video_url,
            })

            # Copy audio to public dir
            public_ep_dir = os.path.join(config.podcast_output_dir, "episodes")
            os.makedirs(public_ep_dir, exist_ok=True)
            shutil.copy2(audio_path, os.path.join(public_ep_dir, audio_filename))

            # Rebuild channel-specific RSS feed
            all_episodes = tracker.get_all_processed()
            # Filter by channel
            channel_eps = [
                ep for ep in all_episodes.values()
                if ep.get("channel") == channel.name
            ]
            sorted_eps = sorted(channel_eps, key=lambda e: e.get("published", ""))

            feed = build_channel_feed(config, channel, sorted_eps)
            save_feed(feed, channel.feed_path)

            # Also update the unified feed
            unified_feed_path = os.path.join(config.podcast_output_dir, config._data.get("podcast", {}).get("feed_filename", "feed.xml"))
            all_sorted = sorted(all_episodes.values(), key=lambda e: e.get("published", ""))
            unified_feed = build_unified_feed(config, all_sorted)
            save_feed(unified_feed, unified_feed_path)

            logger.info("[%s] Successfully processed: %s", channel.name, video_title)
            result["processed"].append({
                "id": video_id,
                "title": video_title,
                "channel": channel.name,
                "audio_file": audio_filename,
                "duration": audio_result.get("duration_seconds", 0),
                "voice": channel.tts_voice,
            })

        except Exception as e:
            logger.error("[%s] Error processing %s: %s",
                        channel.name, video.get("id", "unknown"), e, exc_info=True)
            result["errors"].append({"id": video.get("id", "unknown"), "reason": str(e)})

    return result


def build_channel_feed(config, channel: ChannelConfig, episodes: list[dict]):
    """Build RSS feed for a specific channel."""
    feed = create_feed(
        title=channel.podcast_title,
        description=channel.podcast_description,
        author=channel.podcast_author,
        language=config.podcast_language,
        website=config.podcast_website,
        feed_filename=channel.feed_filename,
    )
    for ep in episodes:
        audio_filename = ep.get("audio_file", "")
        audio_path = os.path.join(config.podcast_episodes_dir, audio_filename) if audio_filename else ""
        audio_url = f"{config.podcast_website.rstrip('/')}/episodes/{audio_filename}" if audio_filename else ""
        try:
            published = datetime.fromisoformat(ep["published"]) if "published" in ep else datetime.now()
        except (ValueError, TypeError):
            published = datetime.now()
        episode_desc = f"{channel.name} 最新视频《{ep.get('title', '')}》的中文同音翻译播客版本。"
        add_episode(
            feed,
            title=f"【{channel.podcast_title}】{ep.get('title', '')}",
            description=episode_desc,
            audio_path=audio_path,
            audio_url=audio_url,
            duration=int(ep.get("duration_seconds", 0)),
            published=published,
            video_url=ep.get("url", ""),
        )
    return feed


def build_unified_feed(config, episodes: list[dict]):
    """Build a unified RSS feed with all channels."""
    feed = create_feed(
        title="AI 播客精选合集",
        description="Matt Wolfe、Lenny's Podcast、Dwarkesh Patel、Andrej Karpathy 等频道的中文播客合集",
        author="AI 播客工坊",
        language=config.podcast_language,
        website=config.podcast_website,
        feed_filename="feed.xml",
    )
    for ep in episodes:
        audio_filename = ep.get("audio_file", "")
        audio_path = os.path.join(config.podcast_episodes_dir, audio_filename) if audio_filename else ""
        audio_url = f"{config.podcast_website.rstrip('/')}/episodes/{audio_filename}" if audio_filename else ""
        try:
            published = datetime.fromisoformat(ep["published"]) if "published" in ep else datetime.now()
        except (ValueError, TypeError):
            published = datetime.now()
        channel_name = ep.get("channel", "")
        episode_desc = f"{channel_name} 视频《{ep.get('title', '')}》的中文播客版本。"
        add_episode(
            feed,
            title=f"【{channel_name}】{ep.get('title', '')}",
            description=episode_desc,
            audio_path=audio_path,
            audio_url=audio_url,
            duration=int(ep.get("duration_seconds", 0)),
            published=published,
            video_url=ep.get("url", ""),
        )
    return feed


def run_daily(dry_run: bool = False) -> dict:
    """
    Daily processing pipeline across all channels.

    1. For each channel: check for new videos
    2. Download subtitles for unprocessed videos
    3. Translate to Chinese
    4. Generate TTS audio (per-channel voice)
    5. Update per-channel RSS feed + unified feed

    Args:
        dry_run: If True, only check for new videos.

    Returns:
        dict with summary of what was done.
    """
    config = get_config()
    ensure_dirs(config)
    tracker = ProcessedTracker()

    overall = {
        "date": datetime.now().isoformat(),
        "channels_checked": len(config.channels),
        "results": [],
        "total_new": 0,
        "total_processed": 0,
        "total_errors": 0,
    }

    for channel in config.channels:
        logger.info("=" * 50)
        logger.info("Processing channel: %s", channel.name)
        logger.info("=" * 50)
        ch_result = process_channel(channel, tracker, dry_run=dry_run)
        overall["results"].append(ch_result)
        overall["total_new"] += ch_result["new_videos_found"]
        overall["total_processed"] += len(ch_result["processed"])
        overall["total_errors"] += len(ch_result["errors"])

    return overall


def get_status() -> dict:
    """Get processing status summary across all channels."""
    config = get_config()
    tracker = ProcessedTracker()
    processed = tracker.get_all_processed()

    channel_stats = {}
    for channel in config.channels:
        channel_eps = [
            ep for ep in processed.values()
            if ep.get("channel") == channel.name
        ]
        times = [ep["processed_at"] for ep in channel_eps if "processed_at" in ep]
        channel_stats[channel.name] = {
            "count": len(channel_eps),
            "last_processed": max(times) if times else "never",
            "feed_path": channel.feed_path,
            "feed_exists": os.path.exists(channel.feed_path),
        }

    return {
        "total_processed": len(processed),
        "channel_stats": channel_stats,
        "episodes_dir": config.podcast_episodes_dir,
        "output_dir": config.podcast_output_dir,
        "unified_feed": os.path.join(config.podcast_output_dir,
                                      config._data.get("podcast", {}).get("feed_filename", "feed.xml")),
    }
