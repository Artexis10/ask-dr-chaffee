#!/usr/bin/env python3
"""
Test Chaffee voice profile against given YouTube URLs.
Downloads a short segment, converts to 16kHz WAV, extracts embeddings, and
compares to the saved profile.
"""
import os
import sys
import re
import json
import math
import tempfile
import subprocess
import shutil
import logging
from urllib.parse import urlparse, parse_qs

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.append(PROJECT_ROOT)

from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


def parse_start_time_seconds(url: str) -> int:
    # Supports t=9s or t=1949s or t=MMmSSs; YouTube uses seconds typically
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    t = q.get('t', [None])[0]
    if not t:
        return 0
    # Accept forms like '1949s' or '90' or '1m23s'
    try:
        if t.endswith('s') and t[:-1].isdigit():
            return int(t[:-1])
        # 1m23s
        m = re.match(r'(?:(\d+)m)?(?:(\d+)s)?$', t)
        if m:
            minutes = int(m.group(1) or 0)
            seconds = int(m.group(2) or 0)
            return minutes * 60 + seconds
        # plain seconds
        return int(t)
    except Exception:
        return 0


def download_segment_to_wav(url: str, out_dir: str, start_sec: int = 0, duration_sec: int = 30) -> str:
    # Prepare paths
    video_id = 'clip'
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    if 'v' in q:
        video_id = q['v'][0]
    m4a_path = os.path.join(out_dir, f"{video_id}.m4a")
    wav_path = os.path.join(out_dir, f"{video_id}.wav")

    # ffmpeg path
    ffmpeg_dir = os.path.join(PROJECT_ROOT, 'backend', 'ffmpeg', 'ffmpeg-master-latest-win64-gpl', 'bin')
    ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
    env = os.environ.copy()
    if os.path.exists(ffmpeg_exe):
        env['PATH'] = ffmpeg_dir + os.pathsep + env.get('PATH', '')

    # 1) Download audio as m4a
    ytdlp_cmd = [
        'yt-dlp', '-f', '140/bestaudio',
        '--no-check-certificate', '--no-playlist',
        '-o', m4a_path,
        url
    ]
    log.info(f"Downloading: {' '.join(ytdlp_cmd)}")
    subprocess.run(ytdlp_cmd, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')

    if not os.path.exists(m4a_path) or os.path.getsize(m4a_path) < 1024:
        raise RuntimeError(f"Downloaded file invalid: {m4a_path}")

    # 2) Convert segment to 16kHz mono WAV
    # Use -ss before -i for faster seek when possible, but compatibility matters.
    ffmpeg_cmd = [
        ffmpeg_exe if os.path.exists(ffmpeg_exe) else 'ffmpeg',
        '-y', '-ss', str(start_sec), '-t', str(duration_sec),
        '-i', m4a_path,
        '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
        wav_path
    ]
    log.info(f"Converting: {' '.join(ffmpeg_cmd)}")
    subprocess.run(ffmpeg_cmd, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')

    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1024:
        raise RuntimeError(f"WAV conversion failed: {wav_path}")

    return wav_path


def score_url_against_profile(profile_name: str, url: str, segment_sec: int = 30) -> dict:
    enrollment = VoiceEnrollment(voices_dir='voices')
    profile_embeddings = enrollment.load_profile(profile_name)
    if not profile_embeddings:
        raise RuntimeError(f"Profile embeddings not found for {profile_name}")

    tmp_dir = tempfile.mkdtemp(prefix='verify_')
    try:
        start_sec = parse_start_time_seconds(url)
        wav_path = download_segment_to_wav(url, tmp_dir, start_sec=start_sec, duration_sec=segment_sec)

        test_embs = enrollment._extract_embeddings_from_audio(wav_path)
        if not test_embs:
            return { 'url': url, 'error': 'no_embeddings' }

        # Compute similarity of each test embedding vs profile (list)
        sims = []
        for e in test_embs:
            sim = enrollment.compute_similarity(e, profile_embeddings)
            sims.append(float(sim))

        sims.sort(reverse=True)
        avg = sum(sims) / len(sims)
        top3 = sims[:3] if len(sims) >= 3 else sims
        return {
            'url': url,
            'count': len(test_embs),
            'avg_sim': avg,
            'max_sim': sims[0],
            'top3_avg': sum(top3)/len(top3),
        }
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def main():
    profile = 'Chaffee'
    urls = [
        'https://www.youtube.com/watch?v=x6XSRbuBCd4&t=9s',
        'https://www.youtube.com/watch?v=1oKru2X3AvU&t=1949s',
    ]
    results = []
    for u in urls:
        try:
            res = score_url_against_profile(profile, u, segment_sec=30)
            results.append(res)
            logging.info(json.dumps(res, indent=2))
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed for {u}: {e}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}")
        except Exception as e:
            logging.error(f"Failed {u}: {e}")

if __name__ == '__main__':
    main()
