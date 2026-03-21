import os
import sys
import time
import subprocess
import socket
import urllib.request
import urllib.parse
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

            # Open Netflix in a NEW WINDOW (not a tab) so the existing window stays untouched
            context = browser.new_context()
            page = context.new_page()
            
            # Ensure the browser tab is focused and brought to front
            page.bring_to_front()

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


def play_disney_plus_movie(movie_name: str) -> bool:
    """
    Opens Disney+, searches for a movie/series, and clicks the first result.
    Launches Chrome automatically with a dedicated Jeeves profile.
    """
    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")

            # Use existing context, open a new tab for Disney+
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            # Ensure the browser tab is focused and brought to front
            page.bring_to_front()

            logger.info(f"Opening Disney+ search...")
            page.goto("https://www.disneyplus.com/search")
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(4)

            # Handle Disney+ profile picker if it appears
            try:
                profile_avatars = page.locator('[data-testid="profile-avatar"]')
                if profile_avatars.count() > 0:
                    logger.info(f"Disney+ profile picker detected ({profile_avatars.count()} profiles). Clicking first profile...")
                    profile_avatars.first.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    time.sleep(3)
                    # Re-navigate to search after profile selection
                    page.goto("https://www.disneyplus.com/search")
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    time.sleep(3)
            except Exception as e:
                logger.debug(f"No profile picker found or failed: {e}")

            # Type search query into the search input
            logger.info(f"Typing search query: {movie_name}")
            search_selectors = [
                'input[type="search"]',
                'input[aria-label*="earch"]',
                'input[placeholder*="earch"]',
                'input[data-testid="search-input"]',
                'input[name="q"]',
            ]
            search_input = None
            for sel in search_selectors:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    search_input = loc.first
                    logger.info(f"Found search input via '{sel}'")
                    break

            if not search_input:
                # Fallback: try clicking the search icon first
                logger.warning("Search input not found directly, trying to click search area...")
                try:
                    page.locator('[data-testid="search-icon"]').first.click()
                    time.sleep(2)
                except Exception:
                    pass
                # Try again
                for sel in search_selectors:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        search_input = loc.first
                        break

            if search_input:
                search_input.click()
                time.sleep(0.5)
                search_input.fill(movie_name)
                time.sleep(3)  # Wait for results to appear
            else:
                logger.error("Could not find Disney+ search input!")
                return False

            # Click first search result
            logger.info("Looking for search results...")
            result_selectors = [
                'a[data-testid="search-result"]',
                'a[data-testid="collection-item"]',
                '[data-testid="search-results"] a',
                '.search-results a',
                'a[href*="/video/"]',
                'a[href*="/movies/"]',
                'a[href*="/series/"]',
            ]
            clicked = False
            for rs in result_selectors:
                loc = page.locator(rs)
                if loc.count() > 0 and loc.first.is_visible():
                    card_label = loc.first.get_attribute("aria-label") or loc.first.inner_text()[:50] or "first result"
                    logger.info(f"Found result via '{rs}': '{card_label}', clicking...")
                    loc.first.click()
                    clicked = True
                    break

            if not clicked:
                # Generic fallback: find any clickable card-like element in search area
                logger.warning("No result via specific selectors. Trying generic image/link fallback...")
                try:
                    # Disney+ search results are often images wrapped in links
                    generic = page.locator('section a').first
                    if generic.is_visible():
                        generic.click()
                        clicked = True
                except Exception:
                    pass

            if clicked:
                time.sleep(3)
                logger.info(f"Successfully navigated to '{movie_name}' on Disney+.")
            else:
                logger.warning(f"Could not click any search result for '{movie_name}'.")
                return False

            # Try to auto-play
            play_selectors = [
                'button[data-testid="play-button"]',
                'a[data-testid="play-button"]',
                'button[aria-label*="Play"]',
                'button[aria-label*="play"]',
                'a[href*="/video/"]',
            ]
            played = False
            for ps in play_selectors:
                loc = page.locator(ps)
                if loc.count() > 0 and loc.first.is_visible():
                    logger.info(f"Found Play button via '{ps}', starting playback...")
                    loc.first.click()
                    played = True
                    break

            if not played:
                logger.info("No Play button found — user is on the detail page.")

            logger.info("Script finished. Leaving browser open for watching.")
            return True

    except Exception as e:
        logger.exception("Failed to automate Disney+:")
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

            # Use existing context, open a new tab for YouTube
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            # Ensure the browser tab is focused and brought to front
            page.bring_to_front()

            logger.info(f"Opening YouTube search for: {video_name}")
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(video_name)}"
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
            
            # Find first video result and navigate directly to its URL
            # (clicking the title link is unreliable because YouTube's sticky
            #  masthead bar intercepts pointer events)
            first_result_selector = 'ytd-video-renderer a#video-title'
            logger.debug(f"Looking for results: {first_result_selector}")
            page.wait_for_selector(first_result_selector, timeout=15000)
            
            first_card = page.locator(first_result_selector).first
            card_label = first_card.get_attribute("title") or "unknown"
            video_href = first_card.get_attribute("href")
            logger.info(f"Found first result: '{card_label}', navigating to video...")

            if video_href:
                # Build absolute URL and navigate directly
                video_url = f"https://www.youtube.com{video_href}" if video_href.startswith("/") else video_href
                page.goto(video_url)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            else:
                # Fallback: force-click if href not available
                logger.warning("No href found, falling back to force-click...")
                first_card.click(force=True)

            logger.info(f"Successfully started playing '{card_label}'.")

            # Keep browser alive for watching
            return True

    except Exception as e:
        logger.exception("Failed to automate YouTube:")
        return False


def play_youtube_music(query: str) -> bool:
    """
    Opens YouTube Music, searches for a song/artist, and plays the first result.
    Launches Chrome automatically with a dedicated Jeeves profile.
    """
    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")

            # Use existing context, open a new tab for YouTube Music
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            # Ensure the browser tab is focused and brought to front
            page.bring_to_front()

            logger.info(f"Opening YouTube Music search for: {query}")
            search_url = f"https://music.youtube.com/search?q={urllib.parse.quote_plus(query)}"
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
            time.sleep(2)
            
            # Find the top result play button or the first song
            play_selectors = [
                'ytmusic-card-shelf-renderer .ytmusic-play-button-renderer',  # Top result play button
                'ytmusic-immersive-header-renderer .ytmusic-play-button-renderer', # Artist page
                'ytmusic-responsive-list-item-renderer .ytmusic-play-button-renderer', # First playlist/song
            ]
            
            played = False
            for selector in play_selectors:
                elements = page.locator(selector)
                if elements.count() > 0 and elements.first.is_visible():
                    logger.info(f"Found play button via '{selector}', clicking...")
                    # ensure we evaluate click from within the page to bypass pointer intercepts
                    elements.first.click(force=True)
                    played = True
                    break

            if played:
                logger.info(f"Successfully started playing music for '{query}'.")
            else:
                logger.warning(f"Could not find a play button for '{query}' on YT Music. Trying generic click.")
                # click any prominent play button
                try:
                    page.locator('#play-button').first.click(force=True)
                    logger.info("Clicked generic play button")
                except Exception as e:
                    pass
            
            return True

    except Exception as e:
        logger.exception("Failed to automate YouTube Music:")
        return False


def stop_youtube_video() -> bool:
    """
    Stops (pauses) the currently playing YouTube video.
    Finds the YouTube tab and presses 'k' (YouTube's pause/play shortcut).
    """
    if not _is_port_open(CHROME_DEBUG_PORT):
        logger.info("Chrome is not running, nothing to stop.")
        return True

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")
            if not browser.contexts:
                return True
            context = browser.contexts[0]

            # Find the tab playing YouTube
            for page in context.pages:
                if "youtube.com" in page.url:
                    logger.info(f"Found YouTube tab: {page.url}")
                    page.bring_to_front()

                    # Use JavaScript to pause all HTML5 video elements. This is much 
                    # more reliable than focus + keyboard shortcuts.
                    try:
                        page.evaluate("document.querySelectorAll('video').forEach(v => v.pause());")
                        
                        # Also click the explicit pause button on YT music if present, 
                        # sometimes JS pause isn't enough to update the UI
                        pause_btn = page.locator('#play-pause-button')
                        if pause_btn.count() > 0 and pause_btn.first.get_attribute('aria-pressed') == 'true':
                           pause_btn.first.click(force=True)
                           
                    except Exception as e:
                        logger.warning(f"Error pausing via JS/button: {e}")
                        # Fallback to keyboard shortcut just in case
                        page.keyboard.press("k")

                    logger.info("YouTube playback stopped.")
                    return True

            logger.info("No active YouTube tab found.")
            return True

    except Exception as e:
        logger.exception("Failed to stop YouTube video:")
        return False


def play_beatrix_exercises() -> bool:
    """
    Opens the specified Wibbi exercise portal for Beatrix.
    Launches Chrome automatically with a dedicated Jeeves profile.
    """
    if not _ensure_chrome_running():
        return False

    try:
        with sync_playwright() as p:
            logger.info(f"Connecting Playwright to Chrome CDP at 127.0.0.1:{CHROME_DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")

            # Use existing context, open a new tab for Beatrix
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            # Ensure the browser tab is focused and brought to front
            page.bring_to_front()

            logger.info("Opening Beatrix Exercises portal on Wibbi...")
            # Target URL
            target_url = "https://patient-portal-v2.wibbi.com/resources/program/39807114/exercises"
            page.goto(target_url)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(3)
            
            logger.info("Beatrix Exercises portal loaded successfully.")
            return True

    except Exception as e:
        logger.exception("Failed to automate Beatrix Exercises:")
        return False


def _ensure_mavis_server() -> bool:
    """Check if local port 8777 is open. If not, start server.py."""
    if _is_port_open(8777):
        logger.info("Mavis server is already running on port 8777.")
        return True

    logger.info("Starting Mavis server on port 8777...")
    server_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
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
            page = context.new_page()

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

def control_metronome(action: str, bpm: int = None) -> bool:
    """
    Controls the local metronome HTML application.
    action: "start", "stop", or "set_bpm"
    bpm: optional integer for the BPM
    """
    if not _ensure_chrome_running():
        return False

    metronome_path = r"C:\Users\Vladimir\.gemini\antigravity\scratch\metronome\index.html"
    metronome_url = f"file:///{metronome_path.replace(chr(92), '/')}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            
            # Find the metronome tab if it's already open
            metronome_page = None
            for page in context.pages:
                if "metronome/index.html" in page.url or metronome_url in page.url:
                    metronome_page = page
                    break
            
            # If not open, open it
            if not metronome_page:
                metronome_page = context.new_page()
                metronome_page.goto(metronome_url)
                metronome_page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
            
            metronome_page.bring_to_front()

            # Perform the action
            if action == "set_bpm" or bpm is not None:
                if bpm is not None:
                    bpm_input = metronome_page.locator("#bpm-input")
                    bpm_input.fill(str(bpm))
                    bpm_input.evaluate("el => el.dispatchEvent(new Event('change'))")
                    logger.info(f"Metronome BPM set to {bpm}")
            
            play_btn = metronome_page.locator("#play-btn")
            is_playing = "playing" in play_btn.get_attribute("class", timeout=1000) or False

            if action == "start" and not is_playing:
                play_btn.click()
                logger.info("Metronome started")
            elif action == "stop" and is_playing:
                play_btn.click()
                logger.info("Metronome stopped")

            return True

    except Exception as e:
        logger.exception(f"Failed to control metronome (action={action}, bpm={bpm}):")
        return False



if __name__ == "__main__":
    logger.info("Testing browser controller module...")
    play_netflix_movie("Matrix")
