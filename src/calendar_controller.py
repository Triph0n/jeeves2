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

# Friendly name -> calendar ID mapping
CALENDAR_ALIASES = {
    'rodina': 'family14259236500433336005@group.calendar.google.com',
}

def resolve_calendar_id(calendar_name: str = "") -> str:
    """Resolves a friendly calendar name to its Google ID.
    Returns 'primary' when no name is given."""
    if not calendar_name:
        return 'primary'
    key = calendar_name.strip().lower()
    if key in CALENDAR_ALIASES:
        return CALENDAR_ALIASES[key]
    # If unknown, assume it's already an ID
    return calendar_name

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

def create_event(summary: str, start_time: str, end_time: str, description: str = "", calendar_name: str = ""):
    """
    Creates an event in Google Calendar.
    If calendar_name is given (e.g. 'Rodina'), writes to that calendar.
    Otherwise writes to the primary calendar.
    start_time and end_time should be ISO 8601 strings (e.g. '2026-03-10T10:00:00+01:00').
    """
    service = get_calendar_service()
    if not service:
        return "Nelze se připojit k Google Kalendáři. Zkontrolujte přihlašovací údaje."

    cal_id = resolve_calendar_id(calendar_name)

    event = {
      'summary': summary,
      'description': description,
      'start': {
        'dateTime': start_time,
        'timeZone': 'Europe/Prague',
      },
      'end': {
        'dateTime': end_time,
        'timeZone': 'Europe/Prague',
      },
    }

    try:
        cal_label = calendar_name if calendar_name else 'primary'
        logger.info(f"Vytvářím událost: {summary} v čase {start_time} (kalendář: {cal_label})")
        event = service.events().insert(calendarId=cal_id, body=event).execute()
        return f"Událost '{summary}' byla úspěšně vytvořena v kalendáři '{cal_label}'. Odkaz: {event.get('htmlLink')}"
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        traceback.print_exc()
        return f"Chyba při vytváření události v kalendáři: {e}"

if __name__ == '__main__':
    # Test getting events
    print("Testing Calendar Controller...")
    events = get_upcoming_events(5)
    print(str(events).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
