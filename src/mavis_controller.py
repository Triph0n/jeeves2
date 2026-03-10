import json
import os
import re
import asyncio
from typing import Optional, Dict

import edge_tts
import pygame

from src.logger import logger

# Constants mapped to the existing database
DB_PATH = r"C:\Users\Vladimir\.gemini\antigravity\scratch\knihy-databaze\books_db.json"
BOOKS_DIR = r"C:\Users\Vladimir\Desktop\e-knihy-sbirka-sci-fi-a-fantasy-2254knih-txt-iso-8859-2"
VOICE = "cs-CZ-VlastaNeural"

# Global state for playback control
_current_playback_task = None
_is_playing = False

def load_database() -> Optional[Dict]:
    """Loads the book database JSON file."""
    try:
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load Mavis database: {e}")
        return None

def search_book(query: str) -> Optional[Dict]:
    """Search for a book by title or author."""
    db = load_database()
    if not db or "books" not in db:
        return None
        
    query = query.lower().strip()
    
    # Simple search: Try to find a match in title or author
    best_match = None
    for book in db["books"]:
        title = book.get("title", "").lower()
        author = book.get("author", "").lower()
        
        if query in title or query in author:
            # Prefer title matches if possible
            if not best_match or query in title:
                best_match = book
                # If exact match, stop searching
                if query == title:
                    break
                    
    return best_match

def read_book_content(book_path_rel: str) -> str:
    """Reads the book content from the filesystem."""
    try:
        full_path = os.path.join(BOOKS_DIR, book_path_rel)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Book file not found: {full_path}")
            
        with open(full_path, 'r', encoding='iso-8859-2', errors='replace') as f:
            content = f.read()
            
        # Clean up very long headers/metadata blocks often found in these txt files
        content = re.sub(r'^[^\n]*(\n[^\n]*){0,20}\* \* \*\n', '', content, count=1)
        return content
    except Exception as e:
        logger.error(f"Error reading book: {e}")
        return ""

async def _play_text_generator(content: str):
    """Generates audio chapter by chapter and plays it using pygame."""
    global _is_playing
    
    # Split content into smaller chunks (e.g. paragraphs) to avoid huge single generations
    paragraphs = [p.strip() for p in re.split(r'\n\n+', content) if p.strip()]
    
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            
        # Group small paragraphs to reduce API calls
        chunk_size = 800
        current_chunk = ""
        chunks = []
        
        for p in paragraphs:
            if len(current_chunk) + len(p) < chunk_size:
                current_chunk += " " + p
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = p
        if current_chunk:
            chunks.append(current_chunk.strip())

        for i, text_chunk in enumerate(chunks):
            if not _is_playing:
                break
                
            logger.info(f"Mavis generating audio chunk {i+1}/{len(chunks)}...")
            communicate = edge_tts.Communicate(text_chunk, VOICE)
            
            # Save temporary file
            temp_file = os.path.join(os.path.dirname(__file__), "mavis_temp.mp3")
            await communicate.save(temp_file)
            
            if not _is_playing:
                break
                
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            
            # Wait while music is playing
            while pygame.mixer.music.get_busy() and _is_playing:
                await asyncio.sleep(0.5)
                
            # Cleanup temp file if finished
            pygame.mixer.music.unload()
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass
                
    except Exception as e:
        logger.error(f"Mavis playback error: {e}")
    finally:
        _is_playing = False
        logger.info("Mavis playback stopped.")

def start_reading(book_query: str) -> str:
    """Entry point to start reading a book."""
    global _current_playback_task, _is_playing

    logger.info(f"Mavis asked to read: {book_query}")
    book = search_book(book_query)
    
    if not book:
        return f"Mavis nenašla žádnou knihu pro dotaz: '{book_query}'."
        
    book_title = book.get('title', 'Neznámý název')
    book_author = book.get('author', 'Neznámý autor')
    book_path = book.get('path')
    
    content = read_book_content(book_path)
    if not content:
        return f"Mavis se omlouvá, ale soubor pro knihu {book_title} se nepodařilo načíst."

    # Stop any existing playback
    stop_reading()
    
    _is_playing = True
    
    # We create an asyncio task that runs the generator in the background
    # Note: We need to attach this to a running event loop. Since Jeeves relies on 
    # asyncio for its main loop, we can use the current running loop.
    try:
        loop = asyncio.get_running_loop()
        _current_playback_task = loop.create_task(_play_text_generator(content))
        return f"Mavis právě začala číst knihu: {book_title} od autora {book_author}."
    except Exception as e:
        logger.error(f"Failed to start Mavis background task: {e}")
        _is_playing = False
        return "Nastala chyba při spouštění čtečky Mavis."

def stop_reading() -> str:
    """Stops the current book reading."""
    global _is_playing, _current_playback_task
    
    was_playing = _is_playing
    _is_playing = False
    
    if _current_playback_task and not _current_playback_task.done():
        _current_playback_task.cancel()
        _current_playback_task = None
        
    try:
        if pygame.mixer.get_init():
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception:
        pass
        
    if was_playing:
        return "Mavis přestala číst."
    else:
        return "Mavis zrovna nic nečte."
