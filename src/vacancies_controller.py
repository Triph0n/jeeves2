import json
import subprocess
import os
from src.logger import logger

def _run_scraper(script_name):
    """Run a Node.js scraper script and return the parsed JSON data list."""
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scraper_path = os.path.join(script_dir, script_name)
        
        process = subprocess.run(
            ['node', scraper_path],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8'
        )
        
        stdout = process.stdout.strip()
        if not stdout:
            logger.error(f"Scraper {script_name} returned empty output. Stderr: {process.stderr[:200]}")
            return []
        
        data = json.loads(stdout)
        
        if 'error' in data and data['error']:
            logger.error(f"Scraper {script_name} error: {data['error']}")
        
        return data.get('data', [])
        
    except subprocess.TimeoutExpired:
        logger.error(f"Scraper {script_name} timed out after 30s")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from {script_name}: {e}")
    except Exception as e:
        logger.error(f"Failed to run scraper {script_name}: {e}")
    
    return []

def get_muvac_vacancies():
    """Fetch cello vacancies from Muvac via Puppeteer scraper."""
    items = _run_scraper('muvac_scraper.js')
    results = []
    for item in items:
        results.append({
            "title": item.get('name', ''),
            "organization": item.get('organization', ''),
            "url": item.get('url', 'https://www.muvac.com/en/browse/vacancies?query=cello'),
            "source": "Muvac"
        })
    return results

def get_musikzeitung_vacancies():
    """Fetch cello job listings from Schweizer Musikzeitung Stellen via Puppeteer scraper."""
    items = _run_scraper('musikzeitung_scraper.js')
    results = []
    for item in items:
        org = item.get('organization', '')
        category = item.get('category', '')
        subtitle = f"{org}" if org else ""
        if category:
            subtitle = f"{category} — {org}" if org else category
        
        results.append({
            "title": item.get('title', ''),
            "organization": subtitle,
            "url": item.get('url', 'https://www.musikzeitung.ch/stellen/'),
            "source": "Musikzeitung"
        })
    return results

def get_all_vacancies():
    """Získá všechna volná místa z obou zdrojů."""
    muvac = get_muvac_vacancies()
    mz = get_musikzeitung_vacancies()
    return {
        "muvac": muvac,
        "musikzeitung": mz
    }
