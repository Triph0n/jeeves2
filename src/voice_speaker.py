import os
import requests
import pygame
import tempfile
import binascii
from dotenv import load_dotenv
from src.logger import logger

load_dotenv()

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID")

def speak(text: str) -> bool:
    """
    Sends text to MiniMax TTS API and plays the resulting audio.
    """
    if not MINIMAX_API_KEY or MINIMAX_API_KEY == "your_minimax_api_key_here":
        logger.error("MiniMax API key is missing or invalid in .env")
        return False
        
    url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={MINIMAX_GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "speech-01-turbo",
        "text": text,
        "voice_setting": {
            "voice_id": "male-qn-qingse", # Czech/multilingual capable voice
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    }
    
    try:
        logger.info(f"Generating TTS for: '{text}'")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            audio_data = response.json()
            if "data" in audio_data and "audio" in audio_data["data"]:
                audio_hex = audio_data["data"]["audio"]
                audio_bytes = binascii.unhexlify(audio_hex)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    fp.write(audio_bytes)
                    temp_path = fp.name
                    
                logger.debug(f"Saved TTS to {temp_path}")
                play_audio(temp_path)
                os.remove(temp_path)
                return True
            else:
                logger.error(f"Unexpected MiniMax TTS response structure.")
        else:
            logger.error(f"MiniMax API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.exception("Error during TTS generation or playback")
        
    return False

def play_audio(file_path: str):
    """
    Plays an audio file using pygame.
    """
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        logger.exception("Playback error")
    finally:
        pygame.mixer.quit()

if __name__ == "__main__":
    logger.info("Testing voice speaker module...")
    speak("Ahoj, jsem tvůj nový hlasový asistent.")
