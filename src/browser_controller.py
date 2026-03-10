import os
import sys
import time
import subprocess
import socket
import urllib.request
import json
from playwright.sync_api import sync_playwright
from src.logger import logger


# Dedicated Chrome profile for Jeeves - avoids Chrome's security block
# on remote debugging with the default profile directory.
JEEVES_PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "jeeves_chrome_profile"
)

CHROME_DEBUG_PORT = 9222


def _find_chrome() -> str | None:
    """Locate chrome.exe on Windows."""
    for path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]:
        if os.path.exists(path):
            return path
    return None


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _wait_for_chrome_ready(port: int, timeout: int = 15) -> bool:
    """Poll Chrome's CDP endpoint until it responds or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
            data = json.loads(resp.read())
            logger.info(f"Chrome CDP ready! Browser: {data.get('Browser', 'unknown')}")
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _ensure_chrome_running() -> bool:
    """
    Make sure Chrome is running with --remote-debugging-port.
    If it's already listening on the port, reuse it.
    Otherwise, kill any existing Chrome and start a fresh instance
    with a dedicated Jeeves profile directory.
    """
    # 1. Check if Chrome is already running with CDP
    if _is_port_open(CHROME_DEBUG_PORT):
        logger.info(f"Chrome is already listening on port {CHROME_DEBUG_PORT}, reusing it.")
        return True

    # 2. Find Chrome executable
    chrome_path = _find_chrome()
    if not chrome_path:
        logger.error("Chrome executable not found! Install Google Chrome.")
        return False

    # 3. Kill any existing Chrome processes so we can claim the profile lock
    logger.info("Killing existing Chrome processes...")
    os.system("taskkill /F /T /IM chrome.exe >nul 2>&1")
    time.sleep(2)

    # 4. Create the Jeeves profile directory if needed
    os.makedirs(JEEVES_PROFILE_DIR, exist_ok=True)
    logger.info(f"Using Jeeves Chrome profile at: {JEEVES_PROFILE_DIR}")

    # 5. Launch Chrome with our dedicated profile + debug port
    cmd = [
        chrome_path,
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        f"--user-data-dir={JEEVES_PROFILE_DIR}",
        "--remote-allow-origins=*",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    logger.info(f"Starting Chrome: {' '.join(cmd[:3])}...")
    subprocess.Popen(cmd)

    # 6. Wait for Chrome to actually start listening
    logger.info("Waiting for Chrome CDP to become ready...")
    if not _wait_for_chrome_ready(CHROME_DEBUG_PORT, timeout=15):
        logger.error("Chrome started but CDP port never became available!")
        return False

    return True


def play_netflix_movie(movie_name: str) -> bool:
    """
    Opens Netflix, searches for a movie, and clicks play.
    Launches Chrome automatically with a dedicated Jeeves profile.
    """
    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")

            # Use existing context/page or create new ones
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            logger.info(f"Opening Netflix...")
            page.goto("https://www.netflix.com/")
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(3)

            # Handle Netflix profile picker ("Who's watching?")
            profile_links = page.locator('a.profile-link')
            if profile_links.count() > 0:
                logger.info(f"Netflix profile picker detected ({profile_links.count()} profiles). Looking for profile 'V'...")
                
                # Find profile with name "V"
                clicked = False
                for i in range(profile_links.count()):
                    profile_el = profile_links.nth(i)
                    profile_name = profile_el.inner_text().strip()
                    logger.debug(f"  Profile {i}: '{profile_name}'")
                    if profile_name.upper() == "V":
                        logger.info(f"Found profile 'V' at index {i}, clicking...")
                        profile_el.click()
                        clicked = True
                        break
                
                if not clicked:
                    logger.warning("Profile 'V' not found, clicking first profile...")
                    profile_links.first.click()
                
                # Wait for profile picker to disappear and Netflix home to load
                logger.info("Waiting for Netflix home to load after profile selection...")
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(4)

            # Now navigate to search
            logger.info(f"Navigating to Netflix search for: {movie_name}")
            search_url = f"https://www.netflix.com/search?q={movie_name.replace(' ', '%20')}"
            page.goto(search_url)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(4)

            logger.info("Waiting for search results...")
            time.sleep(3)

            # Click first result — Netflix uses data-uia="search-gallery-video-card"
            first_result_selector = 'a[data-uia="search-gallery-video-card"]'
            logger.debug(f"Looking for results: {first_result_selector}")
            page.wait_for_selector(first_result_selector, timeout=15000)
            
            first_card = page.locator(first_result_selector).first
            card_label = first_card.get_attribute("aria-label") or "unknown"
            logger.info(f"Found first result: '{card_label}', clicking...")
            first_card.click()

            logger.info("Waiting for movie detail / mini-modal...")
            time.sleep(3)

            # Try to find and click Play button with multiple strategies
            play_selectors = [
                '[data-uia="play-button"]',
                'a[data-uia="play-button"]',
                'button[data-uia="play-button"]',
                'a[href*="/watch/"]',
            ]
            played = False
            for ps in play_selectors:
                if page.locator(ps).count() > 0 and page.locator(ps).first.is_visible():
                    logger.info(f"Found Play button via '{ps}', starting playback...")
                    page.locator(ps).first.click()
                    played = True
                    break
            
            if not played:
                # Fallback: try role-based search
                logger.warning("Play button not found by data-uia, trying text/role search...")
                try:
                    page.get_by_role("link", name="Play").first.click()
                    played = True
                except Exception:
                    try:
                        page.get_by_role("button", name="Play").first.click()
                        played = True
                    except Exception:
                        logger.error("Could not find any Play button!")

            if played:
                logger.info(f"Successfully started playing '{movie_name}'.")
            else:
                logger.warning(f"Navigated to '{movie_name}' but could not auto-play.")

            # Keep browser alive for watching
            logger.info("Script finished. Leaving browser open for watching.")
            return played

    except Exception as e:
        logger.exception("Failed to automate Netflix:")
        return False


def play_youtube_video(video_name: str) -> bool:
    """
    Opens YouTube, searches for a video, and clicks play on the first result.
    Launches Chrome automatically with a dedicated Jeeves profile.
    """
    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")

            # Use existing context/page or create new ones
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            logger.info(f"Opening YouTube search for: {video_name}")
            search_url = f"https://www.youtube.com/results?search_query={video_name.replace(' ', '+')}"
            page.goto(search_url)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(3)

            # Handle YouTube cookie consent if it appears
            try:
                reject_btn = page.locator('button[aria-label="Reject all"]')
                if reject_btn.count() > 0 and reject_btn.first.is_visible():
                    logger.info("Found YouTube cookie dialog, rejecting all...")
                    reject_btn.first.click()
                    time.sleep(2)
            except Exception as e:
                logger.debug(f"No cookie dialog found or failed to click: {e}")

            logger.info("Waiting for search results...")
            
            # Click first video result
            first_result_selector = 'ytd-video-renderer a#video-title'
            logger.debug(f"Looking for results: {first_result_selector}")
            page.wait_for_selector(first_result_selector, timeout=15000)
            
            first_card = page.locator(first_result_selector).first
            card_label = first_card.get_attribute("title") or "unknown"
            logger.info(f"Found first result: '{card_label}', clicking...")
            first_card.click()

            logger.info(f"Successfully started playing '{card_label}'.")

            # Keep browser alive for watching
            return True

    except Exception as e:
        logger.exception("Failed to automate YouTube:")
        return False


def _ensure_mavis_server() -> bool:
    """Check if local port 8777 is open. If not, start server.py."""
    if _is_port_open(8777):
        logger.info("Mavis server is already running on port 8777.")
        return True

    logger.info("Starting Mavis server on port 8777...")
    server_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knihy-databaze",
        "server.py"
    )
    if not os.path.exists(server_path):
        logger.error(f"Mavis server not found at: {server_path}")
        return False

    # Start the server in the background
    subprocess.Popen(
        [sys.executable, server_path],
        cwd=os.path.dirname(server_path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for the server to spin up
    for _ in range(10):
        if _is_port_open(8777):
            logger.info("Mavis server started successfully.")
            return True
        time.sleep(0.5)
        
    logger.error("Failed to start Mavis server.")
    return False

def play_scifi_book(query: str) -> bool:
    """
    Opens local Sci-Fi database, searches for query, and plays the first book.
    """
    if not _ensure_mavis_server():
        return False

    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            logger.info(f"Opening Sci-Fi Library...")
            page.goto("http://localhost:8777/")
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)

            # Insert search query
            logger.info(f"Searching for: {query}")
            search_input = page.locator("#searchInput")
            search_input.fill(query)
            search_input.press("Enter")
            time.sleep(1)

            # Look for the first book card
            first_book = page.locator(".book-card").first
            if first_book.count() == 0:
                logger.warning(f"No books found for query: {query}")
                return False

            book_title = first_book.locator(".book-title").inner_text()
            logger.info(f"Found book: {book_title}. Opening reader...")
            first_book.click()
            time.sleep(2)

            # Wait for reader and hit play
            logger.info("Starting TTS playback...")
            tts_play_btn = page.locator("#ttsPlay")
            tts_play_btn.wait_for(state="visible", timeout=10000)
            tts_play_btn.click()

            logger.info(f"Mavis starts reading '{book_title}'.")
            return True

    except Exception as e:
        logger.exception("Failed to automate Mavis Sci-Fi Library:")
        return False

def stop_scifi_book() -> bool:
    """Stops the TTS reading in the Sci-Fi library if it's open."""
    if not _is_port_open(CHROME_DEBUG_PORT):
        logger.info("Chrome is not running, nothing to stop.")
        return True

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")
            if not browser.contexts:
                return True
            context = browser.contexts[0]
            
            # Find the tab running localhost:8777
            for page in context.pages:
                if "localhost:8777" in page.url:
                    logger.info("Found Sci-Fi Library tab, stopping playback...")
                    
                    tts_stop_btn = page.locator("#ttsStop")
                    if tts_stop_btn.count() > 0 and tts_stop_btn.is_visible():
                        tts_stop_btn.click()
                        time.sleep(0.5)
                        
                    reader_back_btn = page.locator("#readerBack")
                    if reader_back_btn.count() > 0 and reader_back_btn.is_visible():
                        reader_back_btn.click()
                        
                    return True
            
            logger.info("No active Sci-Fi Library tab found.")
            return True

    except Exception as e:
        logger.exception("Failed to stop Mavis reading:")
        return False



if __name__ == "__main__":
    logger.info("Testing browser controller module...")
    play_netflix_movie("Matrix")
