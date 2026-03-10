# Plán projektu: Inteligentní hlasový asistent pro ovládání PC (Netflix)

**Cíl projektu:** Vytvořit lokální Python aplikaci, která naslouchá hlasovým povelům, pomocí LLM z nich extrahuje záměr, odpoví přirozeným hlasem a pomocí přesné automatizace prohlížeče (Playwright) vykoná akci (např. spustí film na Netflixu).

**Technologický stack:**
- Jazyk: Python
- STT (Hlas na text): Whisper / Google SpeechRecognition
- LLM (Logika): Gemini API (nebo OpenAI / lokální LLM)
- TTS (Text na hlas): MiniMax API (vysoce kvalitní, přirozený hlas)
- Automatizace: Playwright (využívá přesné DOM selektory, nekliká naslepo)

---

## Fáze 1: Základní setup a infrastruktura
- [ ] **1.1:** Inicializace Python projektu. Vytvoření virtuálního prostředí a souboru `requirements.txt` (nebo `pyproject.toml`).
- [ ] **1.2:** Vytvoření základní struktury složek (`src/`, `tests/`) a prázdných souborů pro jednotlivé moduly.
- [ ] **1.3:** Založení souboru `.env` pro bezpečné uložení API klíčů (LLM, MiniMax).
- [ ] **1.4:** Nastavení základního logování (logging) pro sledování běhu aplikace.

## Fáze 2: Hlasová odezva (MiniMax TTS)
*Cíl: Asistent dokáže přirozeně a rychle mluvit.*
- [ ] **2.1:** Instalace knihoven pro přehrávání audia (např. `pygame` nebo `sounddevice`) a `requests`.
- [ ] **2.2:** Vytvoření modulu `voice_speaker.py`.
- [ ] **2.3:** Integrace MiniMax API: Odeslání textu a okamžité přehrání vráceného audio streamu.
- [ ] **2.4:** Otestování: Skript pozdraví uživatele.

## Fáze 3: Přesná automatizace prohlížeče (Playwright)
*Cíl: Skript, který bezpečně a přesně ovládá Netflix pomocí DOM elementů.*
- [ ] **3.1:** Instalace knihovny `playwright` a nezbytných prohlížečů (`playwright install`).
- [ ] **3.2:** Napsání modulu `browser_controller.py`. Skript se musí umět připojit k **existujícímu uživatelskému profilu** (user data dir), abychom nemuseli řešit přihlašování.
- [ ] **3.3:** Implementace funkce `play_netflix_movie(movie_name)`.
    - Přejít na `netflix.com`.
    - Vyčkat na načtení DOM stromu.
    - Najít vyhledávací pole podle přesného selektoru (např. `[data-uia="search-box-input"]`) a vložit název filmu.
    - Najít první výsledek vyhledávání a kliknout na něj.
    - Zajistit spuštění přehrávání (kliknutí na tlačítko "Play").
- [ ] **3.4:** Otestování funkce natvrdo zadaným řetězcem (např. "Matrix").

## Fáze 4: Rozpoznávání hlasu (STT)
*Cíl: Skript nahraje zvuk z mikrofonu a přepíše ho na text.*
- [ ] **4.1:** Instalace knihoven pro práci s audiem (např. `SpeechRecognition`, `pyaudio`, `whisper`).
- [ ] **4.2:** Vytvoření modulu `voice_listener.py`.
- [ ] **4.3:** Implementace naslouchání (např. po stisku klávesy nebo po detekci probouzecího slova) a převod na český text.

## Fáze 5: Inteligentní extrakce záměru (LLM)
*Cíl: Převod textu na strukturovaný povel pro počítač.*
- [ ] **5.1:** Vytvoření modulu `intent_parser.py`.
- [ ] **5.2:** Návrh systémového promptu, který přinutí LLM vracet výhradně JSON ve formátu `{"action": "play_movie", "platform": "netflix", "title": "<název>"}`.
- [ ] **5.3:** Propojení s LLM API (např. Gemini) a otestování parsování na různých frázích (např. "Kámo, pusť mi Inception na netflixu").

## Fáze 6: Finální integrace (Hlavní smyčka)
*Cíl: Propojit všechny moduly do jedné fungující aplikace.*
- [ ] **6.1:** Vytvoření `main.py`.
- [ ] **6.2:** Propojení logiky: 
    1. `voice_listener` zachytí příkaz.
    2. `intent_parser` zjistí, že jde o Netflix a jaký film.
    3. `voice_speaker` odpoví přes MiniMax (např. "Jdu na to, pouštím Matrix.").
    4. `browser_controller` otevře Playwright a film spustí.
- [ ] **6.3:** Ošetření chybových stavů (Film nenalezen, LLM neporozumělo, chyba mikrofonu).