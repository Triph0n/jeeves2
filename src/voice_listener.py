"""
Voice Listener Module - Speech-to-Text (STT)
Captures audio from the microphone and transcribes it to Czech text
using Google Speech Recognition (fast, online) with Whisper as fallback (offline).
"""
import speech_recognition as sr
from src.logger import logger


def listen_for_command(timeout: int = 5, phrase_time_limit: int = 10, language: str = "cs-CZ") -> str | None:
    """
    Listen to the microphone and transcribe speech to text.
    
    Args:
        timeout: Max seconds to wait for speech to begin.
        phrase_time_limit: Max seconds for the phrase itself.
        language: Language code for recognition (default: Czech).
    
    Returns:
        Transcribed text as string, or None if nothing was recognized.
    """
    recognizer = sr.Recognizer()
    
    # Adjust for ambient noise sensitivity
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    
    try:
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            logger.info("Listening... (speak now)")
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit
            )
            
            logger.info("Processing speech...")
            
            # Primary: Google Speech Recognition (fast, online, free)
            try:
                text = recognizer.recognize_google(audio, language=language)
                logger.info(f"Recognized (Google): '{text}'")
                return text
            except sr.UnknownValueError:
                logger.warning("Google could not understand the audio.")
            except sr.RequestError as e:
                logger.warning(f"Google API error: {e}. Trying Whisper fallback...")
            
            # Fallback: Whisper (offline, slower but more accurate for Czech)
            try:
                text = recognizer.recognize_whisper(audio, language="cs", model="base")
                logger.info(f"Recognized (Whisper): '{text}'")
                return text
            except sr.UnknownValueError:
                logger.warning("Whisper could not understand the audio either.")
            except Exception as e:
                logger.error(f"Whisper error: {e}")
            
            return None
            
    except sr.WaitTimeoutError:
        logger.info("No speech detected within timeout.")
        return None
    except OSError as e:
        logger.error(f"Microphone error: {e}")
        logger.error("Make sure a microphone is connected and PyAudio is installed correctly.")
        return None
    except Exception as e:
        logger.exception("Unexpected error in voice listener:")
        return None


def listen_continuous(callback, stop_word: str = "konec", language: str = "cs-CZ"):
    """
    Continuously listen for commands and call the callback function with each one.
    Stops when the stop_word is detected.
    
    Args:
        callback: Function to call with each recognized text.
        stop_word: Word that stops the listening loop.
        language: Language code for recognition.
    """
    logger.info(f"Starting continuous listening. Say '{stop_word}' to stop.")
    
    while True:
        text = listen_for_command(timeout=10, language=language)
        
        if text is None:
            continue
        
        # Check for stop word
        if stop_word.lower() in text.lower():
            logger.info(f"Stop word '{stop_word}' detected. Ending listening.")
            break
        
        callback(text)


if __name__ == "__main__":
    logger.info("Testing voice listener module...")
    logger.info("Say something in Czech (you have 5 seconds)...")
    
    result = listen_for_command()
    
    if result:
        logger.info(f"Final result: '{result}'")
    else:
        logger.info("No speech was recognized.")
