import sys
import os

# Ensure src is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser_controller import play_youtube_video
from src.logger import logger

def test_youtube_playback():
    print("====================================")
    print("Testing YouTube Playback (Rick Roll)")
    print("====================================")
    
    success = play_youtube_video("rick roll")
    
    if success:
        print("[SUCCESS] YouTube playback started successfully.")
    else:
        print("[FAILED] YouTube playback did not start.")
        
if __name__ == "__main__":
    test_youtube_playback()
