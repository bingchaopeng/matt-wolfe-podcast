"""Main orchestrator for Matt Wolfe Chinese podcast automation."""
import os
import logging
from datetime import datetime
from pathlib import Path

from podcast.config import get_config
from podcast.fetcher import get_channel_videos, download_subtitles, extract_text_from_srt, ProcessedTracker
from podcast.translator import get_podcast_script
from podcast.tts import generate_audio_long_text
from podcast.rss import create_feed, add_episode, build_feed_from_history, save_feed

logger = logging.getLogger(__name__)

def ensure_dirs(config):
    """Ensure output and episodes directories exist."""
    os.makedirs(config.podcast_episodes_dir, exist_ok=True)
    os.makedirs(config.podcast_output_dir, exist_ok=True)

def run_daily(dry_run: bool = False) -> dict:
    """
    Daily processing pipeline:
    1. Check for new videos
    2. Download subtitles
    3. Translate to Chinese
    4. Generate TTS audio
    5. Update RSS feed
    6. Mark as processed

    Args:
        dry_run: If True, only check for new videos without processing

    Returns:
        dict with summary of what was done
    """
    config = get_config()
    ensure_dirs(config)
    tracker = ProcessedTracker()

    result = {
        'date': datetime.now().isoformat(),
        'new_videos_found': 0,
        'processed': [],
        'errors': [],
        'skipped': []
    }

    # Step 1: Get latest videos
    logger.info("Checking %s for new videos...", config.channel_name)
    videos = get_channel_videos(config.channel_url, max_results=5, channel_id_override=config.channel_id)
    if not videos:
        logger.warning("No videos found from channel")
        return result

    unprocessed = tracker.get_unprocessed(videos)
    result['new_videos_found'] = len(unprocessed)

    if not unprocessed:
        logger.info("No new videos to process")
        return result

    # Limit to configured max per run
    videos_to_process = unprocessed[:config.max_episodes_per_run]
    logger.info("Processing %d video(s)", len(videos_to_process))

    if dry_run:
        for v in videos_to_process:
            logger.info("[DRY RUN] Would process: %s", v['title'])
            result['processed'].append({
                'id': v['id'],
                'title': v['title'],
                'dry_run': True
            })
        return result

    # Step 2: Process each video
    for video in videos_to_process:
        try:
            video_id = video['id']
            video_title = video['title']
            video_url = video.get('url', "https://www.youtube.com/watch?v={}".format(video_id))

            logger.info("Processing: %s", video_title)

            # Download subtitles
            subs_path = download_subtitles(video_url, config.podcast_episodes_dir)
            if not subs_path or not os.path.exists(subs_path):
                logger.error("No subtitles available for %s", video_id)
                result['errors'].append({'id': video_id, 'reason': 'No subtitles'})
                continue

            # Extract text
            transcript = extract_text_from_srt(subs_path)
            if not transcript:
                logger.error("Empty transcript for %s", video_id)
                result['errors'].append({'id': video_id, 'reason': 'Empty transcript'})
                continue

            # Get video description from fetcher (we can add a simple metadata fetch)
            description = video.get('description', '')

            # Translate and create podcast script (single LLM call)
            logger.info("Translating: %s", video_title)
            podcast_script = get_podcast_script(video_title, description, transcript)

            # Generate audio
            audio_filename = "{}.mp3".format(video_id)
            audio_path = os.path.join(config.podcast_episodes_dir, audio_filename)

            logger.info("Generating audio: %s", audio_filename)
            audio_result = generate_audio_long_text(
                podcast_script,
                audio_path,
                voice=config.tts_voice
            )

            # Audio URL (for RSS enclosure)
            audio_url = "{}/episodes/{}".format(
                config.podcast_website.rstrip("/"), audio_filename
            )

            # Parse published date
            published = datetime.fromisoformat(video['published']) if 'published' in video else datetime.now()

            # Generate episode description
            episode_desc = "Matt Wolfe 最新视频《{}》的中文同音翻译播客版本。".format(video_title)

            # Mark as processed FIRST so it's included in the feed rebuild
            tracker.mark_processed(video_id, {
                'title': video_title,
                'published': video['published'],
                'processed_at': datetime.now().isoformat(),
                'audio_file': audio_filename,
                'duration_seconds': audio_result.get('duration_seconds', 0),
                'url': video_url,
            })

            # Rebuild complete RSS feed from all processed episodes
            feed_path = os.path.join(config.podcast_output_dir, config.feed_filename)
            all_episodes = tracker.get_all_processed()
            # Sort by published date (oldest first for chronological order)
            sorted_eps = sorted(
                all_episodes.values(),
                key=lambda e: e.get("published", ""),
            )
            feed = build_feed_from_history(config, sorted_eps)
            save_feed(feed, feed_path)

            logger.info("Successfully processed: %s", video_title)
            result['processed'].append({
                'id': video_id,
                'title': video_title,
                'audio_file': audio_filename,
                'duration': audio_result.get('duration_seconds', 0)
            })

        except Exception as e:
            logger.error("Error processing video %s: %s", video.get('id', 'unknown'), e, exc_info=True)
            result['errors'].append({'id': video.get('id', 'unknown'), 'reason': str(e)})

    return result

def get_status() -> dict:
    """Get processing status summary."""
    config = get_config()
    tracker = ProcessedTracker()
    processed = tracker.get_all_processed()
    processed_times = [v['processed_at'] for v in processed.values() if 'processed_at' in v]
    return {
        'total_processed': len(processed),
        'channel': config.channel_name,
        'last_processed': max(processed_times, default='never'),
        'episodes_dir': config.podcast_episodes_dir,
        'feed_path': os.path.join(config.podcast_output_dir, config.feed_filename),
        'feed_exists': os.path.exists(os.path.join(config.podcast_output_dir, config.feed_filename))
    }
