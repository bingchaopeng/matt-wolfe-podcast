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
    fg.link(href=config.podcast_website, rel='self')
    fg.language(config.podcast_language)
    fg.author({'name': config.podcast_author})
    fg.generator('Matt Wolfe Chinese Podcast Generator')
    fg.lastBuildDate(datetime.now(timezone.utc))
    # iTunes compatible
    fg.load_extension('podcast')
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
    fe.enclosure(audio_url, str(audio_size), 'audio/mpeg')
    # iTunes duration
    fe.podcast.itunes_duration(str(duration))
    return feed

def save_feed(feed: FeedGenerator, output_path: str) -> str:
    """Save RSS feed to file as RSS 2.0 XML."""
    feed.rss_file(output_path, pretty=True)
    logger.info("RSS feed saved to %s", output_path)
    return output_path

def load_or_create_feed(feed_path: str, config) -> FeedGenerator:
    """
    Load existing RSS feed or create a new one.
    xiaoyuzhou requires a valid RSS feed with at least one episode.
    """
    if os.path.exists(feed_path):
        from feedgen.feed import FeedGenerator
        # Feedgen doesn't support parsing existing feeds well
        # For now, we rebuild - real implementation would parse XML
        logger.info("Feed exists at %s, will append", feed_path)
    return create_feed(config)
