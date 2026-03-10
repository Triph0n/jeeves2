import requests
import logging

logger = logging.getLogger(__name__)

def get_current_weather():
    """
    Získá přibližnou lokaci podle IP adresy a následně stáhne
    aktuální počasí přes z norské meteorologické služby Yr.no.
    Vrácený text je připravený pro Gemini.
    """
    try:
        # 1. Zjistit lokaci
        geo_url = "https://get.geojs.io/v1/ip/geo.json"
        geo_response = requests.get(geo_url, timeout=5)
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        
        lat = geo_data.get("latitude")
        lon = geo_data.get("longitude")
        city = geo_data.get("city")
        country = geo_data.get("country")
        
        if not lat or not lon:
            return "Nepodařilo se mi zjistit tvou přesnou polohu pro předpověď počasí."

        # 2. Zjistit počasí přes Yr.no (Met.no)
        # Met.no VYŽADUJE jedinečný User-Agent s popisem aplikace a kontaktem
        headers = {
            "User-Agent": "JeevesVoiceAssistant/1.0 https://github.com/Triph0n/jeeves2"
        }
        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        weather_response = requests.get(weather_url, headers=headers, timeout=5)
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        
        # Extrakce aktuálních informací
        current_data = weather_data["properties"]["timeseries"][0]["data"]
        details = current_data["instant"]["details"]
        
        temperature = details.get("air_temperature", "N/A")
        wind_speed = details.get("wind_speed", "N/A")
        cloud_area_fraction = details.get("cloud_area_fraction", 0)
        
        # Překlad oblačnosti
        if cloud_area_fraction < 20:
            sky = "jasno"
        elif cloud_area_fraction < 50:
            sky = "polojasno"
        elif cloud_area_fraction < 80:
            sky = "oblačno"
        else:
            sky = "zataženo"
            
        location_name = city if city else "tvé lokaci"

        result = f"Počasí v {location_name} ({country}): {temperature}°C, {sky}, vítr {wind_speed} m/s."
        return result

    except Exception as e:
        logger.error(f"Chyba při získávání počasí: {e}")
        return "Bohužel se mi nepodařilo načíst aktuální údaje o počasí, server s počasím zřejmě neodpovídá."

if __name__ == "__main__":
    import sys
    # Rychlý test
    logging.basicConfig(level=logging.INFO)
    print("Testing Weather Controller...")
    weather = get_current_weather()
    print(str(weather).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
