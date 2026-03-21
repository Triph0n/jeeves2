import urllib.request
import urllib.parse
import json
import datetime
from src.logger import logger

def search_connections(from_location: str, to_location: str, date: str = None, time: str = None) -> str:
    """
    Searches for public transport connections in Switzerland using transport.opendata.ch.
    Returns a formatted string with the next few connections.
    """
    logger.info(f"Searching transport connections from '{from_location}' to '{to_location}' (date={date}, time={time})")
    
    # Build query parameters
    params = {
        "from": from_location,
        "to": to_location,
        "limit": 3  # Get 3 upcoming connections
    }
    if date:
        params["date"] = date
    if time:
        params["time"] = time
        
    query_string = urllib.parse.urlencode(params)
    url = f"https://transport.opendata.ch/v1/connections?{query_string}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JeevesAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        connections = data.get("connections", [])
        if not connections:
            return f"Omlouvám se, ale nenašel jsem žádné spojení z '{from_location}' do '{to_location}'."

        result_lines = [f"Nalezena spojení z {from_location} do {to_location}:"]
        
        for i, conn in enumerate(connections, 1):
            dep = conn.get("from", {})
            arr = conn.get("to", {})
            
            # Formát času: 2026-03-12T10:32:00+0100 -> 10:32
            dep_time_raw = dep.get("departure", "")
            arr_time_raw = arr.get("arrival", "")
            
            dep_time = dep_time_raw[11:16] if len(dep_time_raw) > 16 else "?"
            arr_time = arr_time_raw[11:16] if len(arr_time_raw) > 16 else "?"
            
            duration_raw = conn.get("duration", "") # "00d00:56:00"
            duration = "??"
            if "d" in duration_raw:
                parts = duration_raw.split("d")
                if len(parts) == 2:
                    time_parts = parts[1].split(":") # ["00", "56", "00"]
                    if len(time_parts) >= 2:
                        duration = f"{int(time_parts[0])}h {int(time_parts[1])}m" if int(time_parts[0]) > 0 else f"{int(time_parts[1])} min"

            transfers = conn.get("transfers", 0)
            products = ", ".join(conn.get("products", []))
            platform = dep.get("platform", "")
            platform_str = f" z nástupiště {platform}" if platform else ""
            
            result_lines.append(
                f"{i}. Odjezd {dep_time}{platform_str}, příjezd {arr_time}. "
                f"Doba jízdy {duration}, {transfers} přestupů. (Spoj: {products})"
            )
            
        return "\n".join(result_lines)

    except Exception as e:
        logger.exception(f"Error calling Swiss Transport API:")
        return f"Omlouvám se, při vyhledávání spojení došlo k chybě: {str(e)}"

if __name__ == "__main__":
    # Test
    print(search_connections("Zürich HB", "Bern"))
