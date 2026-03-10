import os.path
import datetime
import traceback
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from src.logger import logger

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json not found! Please download OAuth client ID json from Google Cloud Console.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building calendar service: {e}")
        return None

def get_upcoming_events(max_results=10):
    """
    Returns upcoming events from the primary calendar.
    """
    service = get_calendar_service()
    if not service:
        return "Nelze se připojit k Google Kalendáři. Zkontrolujte přihlašovací údaje."

    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        logger.info(f"Předčítám nadcházející události z Google Kalendáře...")
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            return "V kalendáři nemáš žádné nadcházející události."

        result_lines = ["Nadcházející schůzky:"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Bez názvu')
            result_lines.append(f"{start} - {summary}")
            
        return "\n".join(result_lines)
    
    except Exception as e:
        logger.error(f"Error reading calendar: {e}")
        return f"Chyba při čtení kalendáře: {e}"

def create_event(summary: str, start_time: str, end_time: str, description: str = ""):
    """
    Creates an event in the primary Google Calendar.
    start_time and end_time should be ISO 8601 strings (e.g. '2026-03-10T10:00:00+01:00').
    If timezone is omitted, it will assume local timezone or UTC.
    """
    service = get_calendar_service()
    if not service:
        return "Nelze se připojit k Google Kalendáři. Zkontrolujte přihlašovací údaje."

    event = {
      'summary': summary,
      'description': description,
      'start': {
        'dateTime': start_time,
        'timeZone': 'Europe/Prague', # Assuming typical timezone for the user based on Czech language
      },
      'end': {
        'dateTime': end_time,
        'timeZone': 'Europe/Prague',
      },
    }

    try:
        logger.info(f"Vytvářím událost: {summary} v čase {start_time}")
        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Událost '{summary}' byla úspěšně vytvořena. Odkaz: {event.get('htmlLink')}"
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        traceback.print_exc()
        return f"Chyba při vytváření události v kalendáři: {e}"

if __name__ == '__main__':
    # Test getting events
    print("Testing Calendar Controller...")
    events = get_upcoming_events(5)
    print(str(events).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
