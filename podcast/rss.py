"""Podcast RSS feed generation module for xiaoyuzhou compatibility."""
import os
import logging
from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from typing import Optional

logger = logging.getLogger(__name__)

def create_feed(config) -> FeedGenerator:
    """
    Create a new podcast RSS feed from config.
    Compatible with xiaoyuzhou podcast import format.
    """
    fg = FeedGenerator()
    fg.title(config.podcast_title)
    fg.description(config.podcast_description)
    # self link = feed URL, alternate link = website
    feed_url = "{}/{}".format(config.podcast_website.rstrip("/"), config.feed_filename)
    fg.link(href=feed_url, rel='self')
    fg.link(href=config.podcast_website, rel='alternate')
    fg.language(config.podcast_language)
    fg.author({'name': config.podcast_author})
    fg.generator('Matt Wolfe Chinese Podcast Generator')
    fg.lastBuildDate(datetime.now(timezone.utc))
    # iTunes compatible
    fg.load_extension('podcast')
    fg.podcast.itunes_author(config.podcast_author)
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
    # Audio enclosure
    audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    if audio_size == 0:
        logger.warning("Audio file missing or empty: %s", audio_path)
    fe.enclosure(audio_url, str(audio_size), 'audio/mpeg')
    # iTunes duration
    fe.podcast.itunes_duration(str(duration))
    return feed

def build_feed_from_history(config, episodes: list[dict]) -> FeedGenerator:
    """
    Rebuild the complete RSS feed from all processed episodes.
    Preserves episode history so subscribers see all content.

    Args:
        config: Config instance
        episodes: List of episode dicts from ProcessedTracker, sorted oldest-first.
                  Each dict must have: title, audio_file, duration_seconds, published, url

    Returns:
        FeedGenerator with all episodes added
    """
    feed = create_feed(config)
    for ep in episodes:
        audio_filename = ep.get("audio_file", "")
        audio_path = os.path.join(config.podcast_episodes_dir, audio_filename)
        audio_url = "{}/episodes/{}".format(config.podcast_website.rstrip("/"), audio_filename)
        try:
            published = datetime.fromisoformat(ep["published"]) if "published" in ep else datetime.now()
        except (ValueError, TypeError):
            published = datetime.now()
        episode_desc = "Matt Wolfe 最新视频《{}》的中文同音翻译播客版本。".format(ep.get("title", ""))
        add_episode(
            feed,
            title="【Matt Wolfe 中文播报】{}".format(ep.get("title", "")),
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
    feed.rss_file(output_path, pretty=True)
    logger.info("RSS feed saved to %s", output_path)
    return output_path
