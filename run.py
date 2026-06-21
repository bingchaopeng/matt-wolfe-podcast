#!/usr/bin/env python3
"""
Matt Wolfe Zhong Wen Bo Ke -- CLI entry point.

Usage:
    python run.py run           # Execute daily processing
    python run.py dry-run       # Dry run, no actual processing
    python run.py status        # View processing status
    python run.py list-voices   # List available Chinese TTS voices
"""
import argparse
import logging
import sys
import os

# Ensure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_logging(verbose: bool = False):
    """Configure logging with Chinese-friendly output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def cmd_run(args):
    """Execute daily processing pipeline."""
    from podcast.main import run_daily
    result = run_daily(dry_run=False)
    print()
    print('=' * 50)
    print("Processing complete!")
    print("Channels checked: {}".format(result.get('channels_checked', 0)))
    for ch in result.get('results', []):
        ch_name = ch.get('channel', '?')
        print()
        print("  【{}】".format(ch_name))
        print("    New videos: {}".format(ch['new_videos_found']))
        print("    Processed:  {}".format(len(ch['processed'])))
        if ch['errors']:
            print("    Failed:     {}".format(len(ch['errors'])))
            for e in ch['errors']:
                print("      X {}: {}".format(e['id'], e['reason']))
        if ch['processed']:
            for p in ch['processed']:
                print("    V {}".format(p['title']))
    print('=' * 50)

def cmd_dry_run(args):
    """Dry run: show what would be processed."""
    from podcast.main import run_daily
    result = run_daily(dry_run=True)
    print()
    print('=' * 50)
    print("[DRY RUN] Found {} new video(s)".format(result.get('total_new', 0)))
    for ch in result.get('results', []):
        print()
        print("  【{}】".format(ch.get('channel', '?')))
        print("    New videos: {}".format(ch.get('new_videos_found', 0)))
        for p in ch.get('processed', []):
            print("    - {} ({})".format(p.get('title', '?'), p.get('id', '?')))
    print('=' * 50)

def cmd_status(args):
    """Show processing status."""
    from podcast.main import get_status
    status = get_status()
    print()
    print('=' * 60)
    print("AI 播客 -- Status")
    print('=' * 60)
    print("总处理数: {} videos".format(status['total_processed']))
    print()
    for ch_name, ch_stat in status.get('channel_stats', {}).items():
        print("  【{}】".format(ch_name))
        print("    已处理: {} videos".format(ch_stat['count']))
        print("    最后处理: {}".format(ch_stat['last_processed']))
        print("     Feed: {}".format(ch_stat['feed_path']))
        print("     存在: {}".format('Yes' if ch_stat['feed_exists'] else 'No'))
        print()
    print("音频目录: {}".format(status['episodes_dir']))
    print("输出目录: {}".format(status['output_dir']))
    print('=' * 60)

def cmd_list_voices(args):
    """List available Chinese TTS voices."""
    from podcast.tts import list_available_voices
    voices = list_available_voices()
    print()
    print("Available Chinese voices ({} total):".format(len(voices)))
    print('=' * 50)
    for v in voices:
        gender = v.get('gender', '?')
        name = v.get('short_name', v.get('name', '?'))
        desc = v.get('description', '')
        print("  {} {}".format(gender, name))
        if desc:
            print("      {}".format(desc))
    print('=' * 50)
    print("Recommended: zh-CN-XiaoxiaoNeural (Female, natural and clear, suitable for podcasts)")

def main():
    parser = argparse.ArgumentParser(
        description='Matt Wolfe Chinese Podcast -- auto fetch, translate, TTS, publish'
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # run
    p_run = subparsers.add_parser('run', help='Execute daily processing pipeline')
    p_run.set_defaults(func=cmd_run)

    # dry-run
    p_dry = subparsers.add_parser('dry-run', help='Dry run, check for new videos only')
    p_dry.set_defaults(func=cmd_dry_run)

    # status
    p_status = subparsers.add_parser('status', help='View processing status')
    p_status.set_defaults(func=cmd_status)

    # list-voices
    p_voices = subparsers.add_parser('list-voices', help='List available Chinese TTS voices')
    p_voices.set_defaults(func=cmd_list_voices)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(args.verbose)
    args.func(args)

if __name__ == '__main__':
    main()
