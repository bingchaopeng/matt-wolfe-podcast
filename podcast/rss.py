"""Podcast RSS feed generation module for xiaoyuzhou compatibility."""
import os
import logging
from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from typing import Optional

logger = logging.getLogger(__name__)


def create_feed(
    title: str,
    description: str,
    author: str,
    language: str = "zh-CN",
    website: str = "",
    feed_filename: str = "feed.xml",
    cover_url: str = "",
) -> FeedGenerator:
    """
    Create a new podcast RSS feed.

    Args:
        title: Podcast title.
        description: Podcast description.
        author: Podcast author name.
        language: Language code (default: zh-CN).
        website: Website URL for the podcast.
        feed_filename: RSS feed filename (for self-link URL).
        cover_url: URL to podcast cover image.

    Returns:
        FeedGenerator instance.
    """
    fg = FeedGenerator()
    fg.title(title)
    fg.description(description)
    feed_url = f"{website.rstrip('/')}/{feed_filename}"
    fg.link(href=feed_url, rel="self")
    fg.link(href=website, rel="alternate")
    fg.language(language)
    fg.author({"name": author})
    fg.generator("AI Podcast Generator")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.load_extension("podcast")
    fg.podcast.itunes_author(author)
    # Cover art - required by 小宇宙
    if cover_url:
        fg.podcast.itunes_image(cover_url)
    # Category
    fg.podcast.itunes_category("Technology")
    # Not explicit
    fg.podcast.itunes_explicit("no")
    return fg


def add_episode(feed: FeedGenerator, title: str, description: str,
                audio_path: str, audio_url: str, duration: int,
                published: datetime, video_url: str = "",
                episode_image: str = "") -> FeedGenerator:
    """
    Add an episode to the podcast feed.
    - audio_path: local file path for getting file size
    - audio_url: public URL for the RSS feed
    - duration: in seconds
    """
    fe = feed.add_entry()
    fe.title(title)
    fe.description(description)
    fe.link(href=video_url if video_url else "")
    fe.published(published)
    audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    if audio_size == 0:
        logger.warning("Audio file missing or empty: %s", audio_path)
    fe.enclosure(audio_url, str(audio_size), "audio/mpeg")
    fe.podcast.itunes_duration(str(duration))
    return feed


def build_feed_from_history(config, episodes: list[dict],
                            channel_name: str = "", channel_config=None) -> FeedGenerator:
    """
    Rebuild RSS feed from all processed episodes.

    Args:
        config: Config instance.
        episodes: List of episode dicts, sorted oldest-first.
        channel_name: Channel name for filtering. If empty, builds unified feed.
        channel_config: ChannelConfig for per-channel feed. If None, builds unified.

    Returns:
        FeedGenerator with all episodes added.
    """
    if channel_config:
        feed = create_feed(
            title=channel_config.podcast_title,
            description=channel_config.podcast_description,
            author=channel_config.podcast_author,
            language=config.podcast_language,
            website=config.podcast_website,
            feed_filename=channel_config.feed_filename,
            cover_url=f"{config.podcast_website.rstrip('/')}/cover.jpg",
        )
        title_prefix = f"【{channel_config.podcast_title}】"
        channel_name = channel_config.name
    else:
        feed = create_feed(
            title="AI乐道人生",
            description="Matt Wolfe、Lenny's Podcast、Dwarkesh Patel、Andrej Karpathy 等频道的中文播客精选，AI 乐道，品味人生",
            author="AI 播客工坊",
            language=config.podcast_language,
            website=config.podcast_website,
            feed_filename="feed.xml",
            cover_url=f"{config.podcast_website.rstrip('/')}/cover.jpg",
        )
        title_prefix = ""
        channel_name = ""

    for ep in episodes:
        audio_filename = ep.get("audio_file", "")
        audio_path = os.path.join(config.podcast_episodes_dir, audio_filename) if audio_filename else ""
        audio_url = f"{config.podcast_website.rstrip('/')}/episodes/{audio_filename}" if audio_filename else ""
        try:
            published = datetime.fromisoformat(ep["published"]) if "published" in ep else datetime.now()
        except (ValueError, TypeError):
            published = datetime.now()
        ep_channel = ep.get("channel", channel_name)
        title_text = ep.get("chinese_title") or ep.get("title", "")
        full_title = f"{title_prefix}{title_text}"
        if not title_prefix:
            full_title = f"【{ep_channel}】{title_text}"
        episode_desc = f"{ep_channel} 最新视频《{title_text}》的peter播客版本。"
        add_episode(
            feed,
            title=full_title,
            description=episode_desc,
            audio_path=audio_path,
            audio_url=audio_url,
            duration=int(ep.get("duration_seconds", 0)),
            published=published,
            video_url=ep.get("url", ""),
        )
    return feed


def save_feed(feed: FeedGenerator, output_path: str) -> str:
    """Save RSS feed to file as RSS 2.0 XML."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    feed.rss_file(output_path, pretty=True)
    logger.info("RSS feed saved to %s", output_path)
    return output_path
