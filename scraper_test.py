import urllib.request
import re

url = 'https://www.musikzeitung.ch/stellen/?_sf_s=cello'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        print('Musikzeitung HTML len:', len(html))
        # Vytáhneme kousky obsahující cello
        snips = []
        for match in re.finditer(r'(.{0,40}cello.{0,40})', html, re.IGNORECASE):
            snips.append(match.group(1))
            
        print("Cello mentions:")
        for s in snips[:10]:
            print("...", s.strip().replace('\n',' '), "...")
            
except Exception as e:
    print('Error:', e)
