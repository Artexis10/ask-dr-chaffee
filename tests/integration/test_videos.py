#!/usr/bin/env python3
"""Quick test of video availability"""

import subprocess
import sys

videos = []
failed = []

# Test first 20 videos from the list
test_list = [
    "E1Yk-o8xwjw", "3GlEPRo5yjY", "-pYI_37Xli4", "vKiUYeKpHDs", "NZ6947ZwhYk",
    "93b3-3h5ooc", "x6XSRbuBCd4", "dtmwfWvQeY8", "mz5_HdJk2Ek", "TvcA6WG2q1o",
    "QIKHsdBWCwQ", "1oKru2X3AvU", "KfuGm0nHmlc", "1zaNvzZxEQc", "yVNr42ccgpU",
    "tk3jYFzgJDQ", "SzT10Az2jes", "PL31nbQPgQU", "Q9rQCYEzPR4", "WuSZog5lqq8"
]

for vid in test_list:
    try:
        result = subprocess.run(['yt-dlp', '--simulate', '--quiet', vid], 
                              capture_output=True, timeout=15)
        if result.returncode == 0:
            videos.append(vid)
            print(f"OK {vid}")
        else:
            failed.append(vid)
            print(f"FAIL {vid}: {result.stderr.decode()[:50]}")
    except Exception as e:
        failed.append(vid)
        print(f"FAIL {vid}: {str(e)[:50]}")

print(f"\nWorking: {len(videos)}")
print(f"Failed: {len(failed)}")

# Save working ones
with open('working_videos.txt', 'w') as f:
    for vid in videos:
        f.write(f"{vid}\n")
