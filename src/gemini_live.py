"""
Gemini Live API Module - Real-time voice assistant using WebSocket streaming.
Replaces the separate STT + LLM + TTS pipeline with a single Gemini Live session.
Audio flows: Microphone → Gemini Live → Speaker, with function calling for browser automation.
"""
import asyncio
import os
import sys
import traceback
import logging
import datetime
import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.logger import logger

class ShutdownException(Exception):
    """Raised to trigger a clean shutdown of the Gemini Live session."""
    pass


from src.weather_controller import get_current_weather
from src.calendar_controller import get_upcoming_events, create_event
from src.tasks_controller import add_task, get_tasks
from src.browser_controller import play_netflix_movie as play_netflix, play_disney_plus_movie as play_disney, play_youtube_video as play_youtube, play_youtube_music, stop_youtube_video, play_scifi_book, stop_scifi_book, play_beatrix_exercises, control_metronome
from src.library_controller import search_library, get_books_by_author, get_library_stats
from src.transport_controller import search_connections
from src.web_server import broadcast_event, command_queue, wakeup_event
from src import cost_tracker

load_dotenv()

# Audio settings
INPUT_SAMPLE_RATE = 16000   # Gemini expects 16kHz input
OUTPUT_SAMPLE_RATE = 24000  # Gemini outputs 24kHz
CHANNELS = 1
INPUT_CHUNK_SIZE = 1024     # ~64ms chunks at 16kHz
FORMAT = pyaudio.paInt16

# Gemini model — gemini-2.0-flash has stable function calling support
# Note: gemini-2.5-flash-native-audio-preview has a known bug (1008) with tool calls
MODEL = "gemini-2.5-flash-native-audio-latest"

# System instruction in Czech
SYSTEM_INSTRUCTION = """Jsi Jeeves, inteligentní hlasový asistent pro ovládání počítače. Mluvíš česky, jsi stručný, vtipný a přátelský jako správný britský butler.

Tvé hlavní schopnosti:
- Pouštět filmy a seriály na Netflixu pomocí funkce play_netflix_movie
- Pouštět filmy a seriály na Disney+ pomocí funkce play_disney_plus
- Pouštět videa na YouTube pomocí funkce play_youtube_video
- Číst a zapisovat události do Google Kalendáře (get_upcoming_events, create_event)
- Hledat švýcarská dopravní spojení (vlaky, autobusy) pomocí funkce search_connections
- Sdílet aktuální informace o počasí podle lokace počítače pomocí get_current_weather (POUZE na vyžádání)
- Použít chytrou asistentku 'Mavis' pro předčítání e-knih (sci-fi a fantasy) pomocí funkcí play_scifi_book a stop_scifi_book
- Vyhledávat a analyzovat knihy v lokální databázi Sci-Fi knihovny (funkce search_library, get_books_by_author a get_library_stats)
- Konverzovat s uživatelem v češtině

Když se uživatel ptá na svůj program ("Co mám dnes v plánu?", "Jaké mám schůzky?"), zavolej get_upcoming_events.
Když chce uživatel naplánovat novou schůzku ("Naplánuj mi zítra v 15:00..."), zavolej create_event. Dbej na to, abys správně převedl čas na formát ISO. Dnešní lokální čas je {datetime.datetime.now().isoformat()}
Pokud uživatel řekne, že událost patří do rodinného kalendáře (nebo se týká rodiny, dětí, kroužků, prázdnin apod.), nastav parametr calendar_name na 'Rodina'. Jinak ho nech prázdný a událost se zapíše do hlavního kalendáře.
Když ti uživatel nadiktuje úkol, seznam věcí k nákupu, nebo poznámku, zavolej funkci add_task. Úkoly se ukládají do nástroje Úkoly Google. DŮLEŽITÉ: Při přidávání položek do seznamu NEOPAKUJ zpět, co jsi zapsal, pouze to mlčky udělej a stručně potvrď (např. "Zapsáno.", "Máte to tam.", "Přidáno.").
Když se uživatel zeptá, jaké má úkoly ("Přečti mi úkoly", "Co mám za úkoly?"), zavolej funkci get_tasks a potom mu z nalezených úkolů rozumně a stručně odvyprávěj, co ho čeká.
Když se uživatel ptá na vlak nebo autobus ve Švýcarsku ("Kdy mi jede vlak z Curychu do Bernu?", "Najdi spojení do Ženevy"), zavolej funkci search_connections. Parametry jsou 'from_location' a 'to_location'. Můžeš přidat i datum a čas, pokud je uživatel specifikoval.
Když se uživatel ptá na počasí ("Jak je venku?", "Jaké je počasí?"), zavolej funkci get_current_weather a pak jej sděl uživateli. POZOR: Počasí oznamuj opravdu jen tehdy, když se na to sám zeptá.
Když tě uživatel požádá o čtení sci-fi nebo fantasy knihy (např. "Zavolej Mavis, ať mi přečte Hobita", "Chci číst Foundation od Asimova"), zavolej funkci play_scifi_book s názvem knihy. Až ji zavoláš, odpověz "Předávám slovo Mavis" (nebo podobně).
Když tě uživatel požádá, ať Mavis přestane číst ("Zastav Mavis", "Přestaňte číst"), zavolej funkci stop_scifi_book a potvrď zastavení.
Když se uživatel ptá co máme v databázi, jestli máme nějakou knihu atd., použij search_library. Databáze obsahuje knihy v těchto žánrech: 'sci-fi', 'fantasy', 'humor', 'krimi'. Pokud se uživatel ptá speciálně na humor nebo krimi, předej to jako parametr 'genre'.
Když uživatel chce vědět, co máme od určitého autora, použij get_books_by_author.
Když se ptá na statistiky knihovny (počet knih atd.), použij get_library_stats.
Když uživatel chce pustit film/seriál na Netflixu, zavolej funkci play_netflix.
Když uživatel chce pustit film/seriál na Disney+ (Disney Plus), zavolej funkci play_disney_plus.
Když chce uživatel pustit video, filmový trailer a podobně, zavolej funkci play_youtube.
Když uživatel řekne "pusť hudbu", "pusť písničku" nebo "zahraj (interpret/skladba)", zavolej funkci play_youtube_music. Používá se přednostně pro čistě hudební přání.
Když uživatel řekne "zastav video", "pozastav video", "zastavit YouTube", "vypni hudbu" nebo podobně, zavolej funkci stop_youtube (funguje pro YT i YT Music).
POKUD uživatel řekne pouze "pusť hudbu" nebo "zahraj něco" a ty nevíš co, zeptej se ho nejdříve, co přesně by chtěl slyšet. Teprve po jeho upřesnění použij funkci play_youtube_music.
Když uživatel řekne "Spusť cvičení pro Beatrix" (případně "Pusť Beatrix cvičení" apod.), zavolej funkci play_beatrix_exercises.
Když tě uživatel požádá o spuštění nebo ovládání metronomu (např. "Spusť metronom", "Zastav metronom", "Dej metronom na 120", "Zrychli zlehka" atp.), zavolej funkci control_metronome. Pokud uživatel zadá rychlost, předej ji v parametru bpm. Jinak předej jen akci (start, stop).
Když uživatel řekne "Můžete jít", "konec", "vypni se" nebo "ukonči se", MUSÍŠ zavolat funkci dismiss_jeeves. Nejprve se rozluč (např. "Sbohem, pane.") a IHNED poté zavolej dismiss_jeeves. Tato funkce tě přepne do offline režimu.
Odpovídej krátce a přirozeně, jako by ses bavil s kamarádem.
Při startu konverzace vždy nejprve sám od sebe pozdrav: "Dobrý den, pane." a pak čekej na instrukce."""

# Function declarations for tool use
GET_CURRENT_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Zjistí podle polohy počítače aktuální počasí (teplotu, oblačnost, vítr).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

GET_WEATHER_FORECAST_TOOL = {
    "name": "get_weather_forecast",
    "description": "Zjistí předpověď počasí pro aktuální polohu počítače na následující dny.",
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Počet dní, pro které se má vrátit předpověď (výchozí 3)."
            }
        }
    }
}

PLAY_NETFLIX_TOOL = {
    "name": "play_netflix",
    "description": "Spustí film nebo seriál na Netflixu. Otevře prohlížeč, vyhledá film a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název filmu nebo seriálu k přehrání, např. 'Matrix', 'Stranger Things'"
            }
        },
        "required": ["query"]
    }
}

PLAY_YOUTUBE_TOOL = {
    "name": "play_youtube",
    "description": "Spustí obecné video na YouTube. Otevře prohlížeč, vyhledá video podle názvu a pustí ho. Vhodné pro videa, trailery, rozhovory atd.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název videa nebo tématu k vyhledání a přehrání na YouTube."
            }
        },
        "required": ["query"]
    }
}

PLAY_YOUTUBE_MUSIC_TOOL = {
    "name": "play_youtube_music",
    "description": "Spustí hudbu na YouTube Music. Použij přednostně pro písničky, hudební alba a čistě hudební interprety. Hledá a hraje na rychlé platformě YT Music.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název písničky nebo jméno interpreta, koho si chce uživatel poslechnout."
            }
        },
        "required": ["query"]
    }
}

STOP_YOUTUBE_TOOL = {
    "name": "stop_youtube",
    "description": "Zastaví (pozastaví) právě přehrávané video na YouTube.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

PLAY_BEATRIX_EXERCISES_TOOL = {
    "name": "play_beatrix_exercises",
    "description": "Spustí webovou stránku se cviky pro Beatrix na portálu Wibbi. Použij, když uživatel požádá o spuštění nebo zobrazení cvičení pro Beatrix.",
    "parameters": {
        "type": "object",
        "properties": {},
    }
}

CALL_MAVIS_TOOL = {
    "name": "play_scifi_book",
    "description": "Spustí aplikaci Mavis (Sci-Fi knihovnu) ve webovém prohlížeči a začne předčítat konkrétní knihu. Použij, když uživatel řekne 'Zavolej Mavis ať přečte...' nebo 'Pusť mi audioknihu...'. Parametr query obsahuje název knihy nebo jméno autora.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název knihy nebo jméno autora."
            }
        },
        "required": ["query"]
    }
}

STOP_MAVIS_TOOL = {
    "name": "stop_scifi_book",
    "description": "Zastaví předčítání běžící knihy v Mavis (Sci-Fi knihovně) ve webovém prohlížeči. Použij, když uživatel řekne 'Mavis stop', 'Zastav Mavis', 'Vypni audioknihu' atd.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

# Library DB Tools
SEARCH_LIBRARY_TOOL = {
    "name": "search_library",
    "description": "Vyhledá knihy ve tvé lokální Sci-Fi databázi (Mavis knihovna) podle názvu nebo klíčového slova. Použij když se uživatel ptá, jestli máme nějakou konkrétní knihu nebo knihu o něčem.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název knihy nebo klíčové slovo pro vyhledávání. Lze nechat prázdné, pokud hledáš jen podle žánru."
            },
            "genre": {
                "type": "string",
                "description": "Volitelný filtr podle žánru. Povolené hodnoty: 'sci-fi', 'fantasy', 'humor', 'krimi', 'all'."
            }
        },
        "required": ["query"]
    }
}

GET_AUTHOR_BOOKS_TOOL = {
    "name": "get_books_by_author",
    "description": "Vrátí seznam všech knih v databázi od zadaného autora. Použij když chce uživatel vědět, jaké knihy od konkrétního autora máme.",
    "parameters": {
        "type": "object",
        "properties": {
            "author": {
                "type": "string",
                "description": "Jméno autora."
            }
        },
        "required": ["author"]
    }
}

GET_LIBRARY_STATS_TOOL = {
    "name": "get_library_stats",
    "description": "Vrátí základní statistiky o tvé lokální Sci-Fi databázi (počet knih celkem, počet autorů a zastoupení žánrů). Použij když se tě uživatel zeptá, kolik knih máme celkem v knihovně.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

GET_CALENDAR_EVENTS_TOOL = {
    "name": "get_upcoming_events",
    "description": "Vrátí seznam nadcházejících událostí z uživatelova kalendáře (dnešní a budoucí schůzky).",
    "parameters": {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Maximální počet nadcházejících událostí."
            }
        }
    }
}

CREATE_CALENDAR_EVENT_TOOL = {
    "name": "create_event",
    "description": "Vytvoří novou událost v kalendáři. Pokud je zadaný calendar_name='Rodina', zapíše do rodinného kalendáře.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": { "type": "string", "description": "Název schůzky." },
            "start_time": { "type": "string", "description": "Čas začátku." },
            "end_time": { "type": "string", "description": "Čas konce." },
            "description": { "type": "string", "description": "Volitelný popis." },
            "calendar_name": { "type": "string", "description": "Volitelné: Název cílového kalendáře. Např. 'Rodina' pro rodinný kalendář. Pokud není zadáno, použije se hlavní kalendář." }
        },
        "required": ["summary", "start_time", "end_time"]
    }
}

ADD_TASK_TOOL = {
    "name": "add_task",
    "description": "Přidá nový úkol nebo poznámku do uživatelova seznamu Úkoly Google (Google Tasks). Použij, když chce uživatel zapsat úkol nebo nákupní seznam.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": { "type": "string", "description": "Název úkolu (např. 'Koupit mléko a chleba' nebo 'Zavolat instalatérovi')." },
            "notes": { "type": "string", "description": "Volitelný detailní popis nebo doplňující informace." }
        },
        "required": ["title"]
    }
}

GET_TASKS_TOOL = {
    "name": "get_tasks",
    "description": "Získá aktivní (nedokončené) úkoly ze seznamu Úkoly Google (Google Tasks). Použij, když chce uživatel přečíst nebo vypsat své aktuální úkoly.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

DISMISS_JEEVES_TOOL = {
    "name": "dismiss_jeeves",
    "description": "Přepne Jeevese do offline režimu. Zavolej tuto funkci, když uživatel řekne 'Můžete jít', 'konec', 'vypni se' nebo 'ukonči se'. Nejprve se rozluč a pak zavolej tuto funkci.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

PLAY_DISNEY_PLUS_TOOL = {
    "name": "play_disney_plus",
    "description": "Spustí film nebo seriál na Disney+. Otevře prohlížeč, vyhledá film a pustí ho.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Název filmu nebo seriálu k přehrání na Disney+, např. 'Encanto', 'Mandalorian'"
            }
        },
        "required": ["query"]
    }
}

SEARCH_CONNECTIONS_TOOL = {
    "name": "search_connections",
    "description": "Vyhledá švýcarská dopravní spojení (vlaky, autobusy, lodě) mezi dvěma místy.",
    "parameters": {
        "type": "object",
        "properties": {
            "from_location": {
                "type": "string",
                "description": "Odkud uživatel jede (např. 'Zürich HB', 'Bern', 'Zürich Flughafen')"
            },
            "to_location": {
                "type": "string",
                "description": "Kam uživatel jede (např. 'Basel SBB', 'Genève')"
            },
            "date": {
                "type": "string",
                "description": "Volitelné: Datum ve formátu YYYY-MM-DD (např. '2026-03-12')"
            },
            "time": {
                "type": "string",
                "description": "Volitelné: Čas ve formátu HH:MM (např. '14:30')"
            }
        },
        "required": ["from_location", "to_location"]
    }
}

SHOW_MEDIA_TOOL = {
    "name": "show_media",
    "description": "Sdílí s uživatelem odkaz nebo obrázek ve vizuálním rozhraní Mission Control. Použij tuto funkci pro sdílení užitečných webových odkazů, map, obrázků nebo doporučení k videím/filmům.",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Typ obsahu. Může být buď 'link' nebo 'image'."
            },
            "url": {
                "type": "string",
                "description": "Plná originální URL adresa odkazu nebo obrázku (např. 'https://cs.wikipedia.org/wiki/Kočka_domácí' nebo 'https://example.com/image.jpg')."
            },
            "title": {
                "type": "string",
                "description": "Krátký srozumitelný název odkazu (např. 'Wikipedie: Kočka', 'Mapa spojení')."
            }
        },
        "required": ["type", "url", "title"]
    }
}

CONTROL_METRONOME_TOOL = {
    "name": "control_metronome",
    "description": "Ovládá lokální aplikaci metronom. Pomocí této funkce metronom spustíš, zastavíš nebo změníš jeho rychlost (BPM).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Akce, kterou má metronom provést. Hodnoty: 'start' (spustit), 'stop' (zastavit), 'set_bpm' (změnit rychlost bez změny stavu přehrávání)."
            },
            "bpm": {
                "type": "integer",
                "description": "Volitelné: Cílové tempo v úderech za minutu (BPM). Pokud není zadáno, ponechá se stávající."
            }
        },
        "required": ["action"]
    }
}

# Combining native generic tools and explicit function calling intent tools
ALL_TOOLS = [
    GET_CURRENT_WEATHER_TOOL,
    PLAY_NETFLIX_TOOL,
    PLAY_DISNEY_PLUS_TOOL,
    PLAY_YOUTUBE_TOOL,
    PLAY_YOUTUBE_MUSIC_TOOL,
    STOP_YOUTUBE_TOOL,
    CALL_MAVIS_TOOL,
    STOP_MAVIS_TOOL,
    SEARCH_LIBRARY_TOOL,
    GET_AUTHOR_BOOKS_TOOL,
    GET_LIBRARY_STATS_TOOL,
    GET_CALENDAR_EVENTS_TOOL,
    CREATE_CALENDAR_EVENT_TOOL,
    ADD_TASK_TOOL,
    GET_TASKS_TOOL,
    PLAY_BEATRIX_EXERCISES_TOOL,
    SEARCH_CONNECTIONS_TOOL,
    SHOW_MEDIA_TOOL,
    DISMISS_JEEVES_TOOL,
    CONTROL_METRONOME_TOOL
]

TOOLS = [{"function_declarations": ALL_TOOLS}]


class JeevesLive:
    """Real-time voice assistant powered by Gemini Live API."""
    
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            logger.error("GEMINI_API_KEY is not set in .env!")
            raise ValueError("Missing GEMINI_API_KEY")
        
        self.client = genai.Client(api_key=api_key)
        self.audio = pyaudio.PyAudio()
        self.is_running = False
        self.audio_out_queue = asyncio.Queue()
        self.current_state = "offline"
        
    async def set_state(self, state: str, message: str = ""):
        """Broadcast state changes to Web UI."""
        if self.current_state != state:
            self.current_state = state
            await broadcast_event("state_change", {"state": state})
        if message:
            await broadcast_event("action_log", {"message": message})
        
    async def start(self):
        """Start the Gemini Live session with audio streaming."""
        
        config = {
            "response_modalities": ["AUDIO"],
            "tools": TOOLS,
            "system_instruction": SYSTEM_INSTRUCTION,
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Fenrir"}}},
        }
        
        logger.info("=" * 60)
        logger.info("  JEEVES Live — Gemini Voice Assistant")
        logger.info("  Mluv česky, Jeeves naslouchá. Řekni 'konec' pro ukončení.")
        logger.info("=" * 60)
        
        try:
            async with self.client.aio.live.connect(
                model=MODEL, 
                config=config
            ) as session:
                logger.info("Gemini Live session connected!")
                self.is_running = True
                cost_tracker.start_session()
                
                # Run three tasks concurrently:
                # 1. Capture audio from microphone
                # 2. Play audio responses from Gemini
                # 3. Receive and process responses from Gemini
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._capture_audio(session))
                    tg.create_task(self._play_audio())
                    tg.create_task(self._receive_responses(session))
                    tg.create_task(self._process_web_commands(session))
                        
        except asyncio.CancelledError:
            logger.info("Session cancelled.")
        except ExceptionGroup as eg:
            logger.error(f"TaskGroup crashed with ExceptionGroup: {eg}")
            for e in eg.exceptions:
                if isinstance(e, ShutdownException):
                    logger.info("Session cleanly shut down via web command.")
                elif not isinstance(e, asyncio.CancelledError):
                    logger.error(f"Task error: {e}")
                    traceback.print_exception(type(e), e, e.__traceback__)
        except Exception as e:
            logger.error(f"Gemini Live session error: {e}")
            traceback.print_exception(type(e), e, e.__traceback__)
        finally:
            self.is_running = False
            cost_tracker.end_session()
            asyncio.create_task(self.set_state("offline", "Spojení přerušeno"))
            self.audio.terminate()
            logger.info("Jeeves Live session ended.")
    
    async def _capture_audio(self, session):
        """Capture audio from microphone and send to Gemini Live."""
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=INPUT_CHUNK_SIZE,
        )
        
        logger.info("Microphone active. Listening...")
        await self.set_state("listening", "Naslouchám...")
        
        try:
            while self.is_running:
                # Read audio from microphone (non-blocking via executor)
                data = await asyncio.to_thread(
                    stream.read, INPUT_CHUNK_SIZE, exception_on_overflow=False
                )
                
                # Send raw PCM audio to Gemini
                cost_tracker.track_input(len(data))
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=data,
                        mime_type="audio/pcm;rate=16000"
                    )
                )
        finally:
            stream.stop_stream()
            stream.close()
    
    async def _play_audio(self):
        """Play audio responses from Gemini through speakers."""
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=2048,
        )
        
        try:
            while self.is_running:
                try:
                    audio_data = await asyncio.wait_for(
                        self.audio_out_queue.get(), timeout=0.1
                    )
                    await self.set_state("speaking")
                    await asyncio.to_thread(stream.write, audio_data)
                except asyncio.TimeoutError:
                    if self.current_state == "speaking":
                        await self.set_state("listening")
                    continue
        finally:
            stream.stop_stream()
            stream.close()

    async def _process_web_commands(self, session):
        """Listen for text commands originating from the Web UI."""
        try:
            while self.is_running:
                cmd = await command_queue.get()
                if cmd == "/shutdown":
                    logger.info("Received /shutdown command. Terminating session.")
                    self.is_running = False
                    await self.set_state("offline", "Vypínám...")
                    
                    # Raise a custom exception so TaskGroup cancels its sibling tasks 
                    # (like the blocking session.receive())
                    raise ShutdownException()

                logger.info(f"Sending web command to Gemini: {cmd}")
                await self.set_state("thinking", "Píšu...")
                # Native fast endpoint:
                await session.send(input=cmd, end_of_turn=True)
        except asyncio.CancelledError:
            pass
    
    async def _receive_responses(self, session):
        """Receive and process responses from Gemini Live."""
        while self.is_running:
            async for response in session.receive():
                # Handle audio output
                if response.data is not None:
                    cost_tracker.track_output(len(response.data))
                    self.audio_out_queue.put_nowait(response.data)
                
                # Handle server content (turn completion etc.)
                if response.server_content and response.server_content.turn_complete:
                    logger.debug("Gemini turn complete.")
                
                # Handle function calls
                if response.tool_call:
                    logger.info("Gemini requested tool call!")
                    await self.set_state("thinking", "Zpracovávám požadavek...")
                    await self._handle_tool_calls(session, response.tool_call)
    
    async def _handle_tool_calls(self, session, tool_call):
        """Execute function calls requested by Gemini and send results back."""
        function_responses = []
        
        for fc in tool_call.function_calls:
            logger.info(f"Function call: {fc.name}({fc.args})")
            await self.set_state("thinking", f"Provádím: {fc.name}")
            
            if fc.name == "play_netflix_movie" or fc.name == "play_netflix": # Handle both old and new name
                title = fc.args.get("title", fc.args.get("query", ""))
                logger.info(f"Executing play_netflix('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_netflix, title)
                    result = {
                        "success": success,
                        "message": f"Film '{title}' {'byl úspěšně spuštěn' if success else 'se nepodařilo spustit'} na Netflixu."
                    }
                except Exception as e:
                    logger.error(f"Browser automation error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při spouštění filmu: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "play_disney_plus":
                title = fc.args.get("title", fc.args.get("query", ""))
                logger.info(f"Executing play_disney('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_disney, title)
                    result = {
                        "success": success,
                        "message": f"Film '{title}' {'byl úspěšně spuštěn' if success else 'se nepodařilo spustit'} na Disney+."
                    }
                except Exception as e:
                    logger.error(f"Browser automation error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při spouštění filmu na Disney+: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "play_youtube_video" or fc.name == "play_youtube": # Handle both old and new name
                title = fc.args.get("title", fc.args.get("query", ""))
                logger.info(f"Executing play_youtube('{title}')...")
                
                try:
                    success = await asyncio.to_thread(play_youtube, title)
                    result = {
                        "success": success,
                        "message": f"Video '{title}' {'bylo úspěšně spuštěno' if success else 'se nepodařilo spustit'} na YouTube."
                    }
                except Exception as e:
                    logger.error(f"Browser automation error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při spouštění videa: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "search_connections":
                logger.info("Executing search_connections()...")
                from_loc = fc.args.get("from_location")
                to_loc = fc.args.get("to_location")
                date_str = fc.args.get("date")
                time_str = fc.args.get("time")
                
                try:
                    result_text = await asyncio.to_thread(search_connections, from_loc, to_loc, date_str, time_str)
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"result": result_text}
                        )
                    )
                except Exception as e:
                    logger.error(f"Transport API error: {e}")
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"error": str(e)}
                        )
                    )

            elif fc.name == "get_upcoming_events":
                max_results = int(fc.args.get("max_results", 10))
                logger.info(f"Executing get_upcoming_events({max_results})...")
                
                try:
                    events = await asyncio.to_thread(get_upcoming_events, max_results)
                    result = {
                        "success": True,
                        "events": events
                    }
                except Exception as e:
                    logger.error(f"Calendar error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "create_event":
                summary = fc.args.get("summary", "")
                start_time = fc.args.get("start_time", "")
                end_time = fc.args.get("end_time", "")
                desc = fc.args.get("description", "")
                cal_name = fc.args.get("calendar_name", "")
                logger.info(f"Executing create_event('{summary}', start='{start_time}', end='{end_time}', calendar='{cal_name}')...")
                
                try:
                    msg = await asyncio.to_thread(create_event, summary, start_time, end_time, desc, cal_name)
                    result = {
                        "success": True,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Calendar error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "add_task":
                title = fc.args.get("title", "")
                notes = fc.args.get("notes", "")
                logger.info(f"Executing add_task('{title}')...")
                
                try:
                    msg = await asyncio.to_thread(add_task, title, notes)
                    result = {
                        "success": True,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Tasks error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "get_tasks":
                logger.info(f"Executing get_tasks()...")
                
                try:
                    tasks = await asyncio.to_thread(get_tasks)
                    
                    if not tasks:
                        msg = "Nemáte žádné aktivní úkoly."
                    else:
                        task_titles = [t.get('title', 'Nepojmenovaný úkol') for t in tasks]
                        msg = "Zde jsou nalezené úkoly: " + ", ".join(task_titles)

                    result = {
                        "success": True,
                        "tasks": tasks,
                        "message": msg
                    }
                except Exception as e:
                    logger.error(f"Tasks error: {e}")
                    result = {
                        "success": False,
                        "message": f"Chyba při načítání úkolů: {str(e)}"
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "get_current_weather":
                logger.info("Executing get_current_weather()...")
                
                try:
                    weather = await asyncio.to_thread(get_current_weather)
                    result = {
                        "success": True,
                        "message": weather
                    }
                except Exception as e:
                    logger.error(f"Weather error: {e}")
                    result = {
                        "success": False,
                        "message": str(e)
                    }
                
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response=result
                    )
                )
            elif fc.name == "play_scifi_book":
                query = fc.args.get("query", "")
                logger.info(f"Executing start_mavis_reading('{query}')...")
                
                try:
                    # Run search+start in background to not block Gemini loop
                    success = await asyncio.to_thread(play_scifi_book, query)
                    if success:
                        result = {"success": True, "message": f"Mavis začala číst knihu '{query}'."}
                    else:
                        result = {"success": False, "message": "Nenalezena žádná kniha nebo se nepodařilo otevřít čtečku."}
                except Exception as e:
                    logger.error(f"Mavis start error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "stop_scifi_book":
                logger.info("Executing stop_mavis_reading()...")
                
                try:
                    success = await asyncio.to_thread(stop_scifi_book)
                    if success:
                        result = {"success": True, "message": "Mavis přestala číst a knihovna byla pozastavena."}
                    else:
                        result = {"success": False, "message": "Při zastavování čtečky Mavis došlo k chybě."}
                except Exception as e:
                    logger.error(f"Mavis stop error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "search_library":
                query = fc.args.get("query", "")
                genre = fc.args.get("genre", "all")
                logger.info(f"Executing search_library('{query}', genre='{genre}')...")
                try:
                    books = await asyncio.to_thread(search_library, query, genre)
                    result = {"success": True, "books": books}
                except Exception as e:
                    logger.error(f"Library search error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            elif fc.name == "get_books_by_author":
                author = fc.args.get("author", "")
                logger.info(f"Executing get_books_by_author('{author}')...")
                try:
                    books = await asyncio.to_thread(get_books_by_author, author)
                    result = {"success": True, "books": books}
                except Exception as e:
                    logger.error(f"Library author search error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            elif fc.name == "get_library_stats":
                logger.info(f"Executing get_library_stats()...")
                try:
                    stats = await asyncio.to_thread(get_library_stats)
                    result = {"success": True, "stats": stats}
                except Exception as e:
                    logger.error(f"Library stats error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            
            elif fc.name == "control_metronome":
                action = fc.args.get("action", "start")
                bpm = fc.args.get("bpm")
                if bpm is not None:
                    bpm = int(bpm)
                logger.info(f"Executing control_metronome(action='{action}', bpm={bpm})...")
                
                try:
                    success = await asyncio.to_thread(control_metronome, action, bpm)
                    if success:
                        result = {"success": True, "message": f"Metronom úspěšně provedl akci: {action}."}
                    else:
                        result = {"success": False, "message": "Při ovládání metronomu došlo k chybě."}
                except Exception as e:
                    logger.error(f"Metronome error: {e}")
                    result = {"success": False, "message": str(e)}
                
                function_responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=result)
                )
            elif fc.name == "play_youtube_music":
                query = fc.args.get("query", "")
                logger.info(f"Executing play_youtube_music('{query}')...")
                try:
                    success = await asyncio.to_thread(play_youtube_music, query)
                    result = {"success": success, "message": f"Spouštím hudbu '{query}' na YouTube Music." if success else "Nepodařilo se spustit hudbu."}
                except Exception as e:
                    logger.error(f"YouTube Music error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            elif fc.name == "stop_youtube":
                logger.info("Executing stop_youtube()...")
                try:
                    success = await asyncio.to_thread(stop_youtube_video)
                    result = {"success": success, "message": "Video na YouTube bylo pozastaveno." if success else "Nepodařilo se pozastavit video."}
                except Exception as e:
                    logger.error(f"YouTube stop error: {e}")
                    result = {"success": False, "message": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
            
            elif fc.name == "play_beatrix_exercises":
                logger.info("Executing play_beatrix_exercises()...")
                try:
                    success = await asyncio.to_thread(play_beatrix_exercises)
                    result = {"success": success, "message": f"Pokus o spuštění cvičení pro Beatrix {'byl úspěšný' if success else 'se nezdařil'}."}
                except Exception as e:
                    logger.error(f"Beatrix exercises play error: {e}")
                    result = {"success": False, "error": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))

            elif fc.name == "show_media":
                media_type = fc.args.get("type", "link")
                url = fc.args.get("url", "")
                title = fc.args.get("title", "")
                logger.info(f"Executing show_media(type='{media_type}', url='{url}', title='{title}')...")
                try:
                    await broadcast_event("media_content", {"mediaType": media_type, "url": url, "title": title})
                    result = {"success": True, "message": "Obsah byl úspěšně nasdílen do Mission Control."}
                except Exception as e:
                    logger.error(f"Show media error: {e}")
                    result = {"success": False, "error": str(e)}
                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))

            elif fc.name == "dismiss_jeeves":
                logger.info("Executing dismiss_jeeves() — going offline...")
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response={"success": True, "message": "Jeeves odchází do offline režimu."}
                    )
                )
                # Send tool response first, then shut down
                if function_responses:
                    await session.send_tool_response(function_responses=function_responses)
                    logger.info("Tool response sent. Shutting down session...")
                # Give Gemini a moment to finish any audio farewell
                await asyncio.sleep(2)
                self.is_running = False
                await broadcast_event("jeeves_dismissed", {})
                await self.set_state("offline", "Jeeves odešel. Klikněte na 'Zavolat Jeevese' pro obnovení.")
                raise ShutdownException()

            else:
                logger.warning(f"Unknown function: {fc.name}")
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=fc.name,
                        response={"error": f"Unknown function: {fc.name}"}
                    )
                )
        
        if function_responses:
            await session.send_tool_response(function_responses=function_responses)
            logger.info("Tool response sent back to Gemini.")


async def main():
    """Entry point for Jeeves Live — loops to allow reconnection after dismiss."""
    while True:
        jeeves = JeevesLive()
        await jeeves.start()
        
        # After session ends (dismissed or error), wait for wakeup signal
        logger.info("Jeeves is offline. Waiting for wakeup signal...")
        wakeup_event.clear()
        await wakeup_event.wait()
        logger.info("Wakeup signal received! Starting new session...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Goodbye!")
