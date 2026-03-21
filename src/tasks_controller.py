import os.path
import traceback
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from src.logger import logger

# If modifying these scopes, delete the file tasks_token.json.
SCOPES = ['https://www.googleapis.com/auth/tasks']

def get_tasks_service():
    """Authenticates and returns a Google Tasks API service object."""
    creds = None
    if os.path.exists('tasks_token.json'):
        creds = Credentials.from_authorized_user_file('tasks_token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json not found! Please download OAuth client ID json from Google Cloud Console.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('tasks_token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('tasks', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error building tasks service: {e}")
        return None


def find_or_create_tasklist(service, title: str) -> str | None:
    """
    Finds a task list by title. If it doesn't exist, creates it.
    Returns the task list ID, or None on error.
    """
    try:
        result = service.tasklists().list(maxResults=100).execute()
        for tl in result.get('items', []):
            if tl.get('title', '').strip().lower() == title.strip().lower():
                logger.info(f"Nalezen existující seznam: '{title}' (id={tl['id']})")
                return tl['id']

        # Not found — create it
        logger.info(f"Seznam '{title}' nenalezen, vytvářím nový...")
        new_list = service.tasklists().insert(body={'title': title}).execute()
        logger.info(f"Vytvořen nový seznam: '{title}' (id={new_list['id']})")
        return new_list['id']
    except Exception as e:
        logger.error(f"Chyba při hledání/vytváření seznamu '{title}': {e}")
        traceback.print_exc()
        return None


def add_task(title: str, notes: str = "", tasklist_name: str = "") -> str:
    """
    Creates a new task. If tasklist_name is given, adds to that named list
    (creating it if needed). Otherwise adds to the default list.
    """
    service = get_tasks_service()
    if not service:
        return "Nelze se připojit k Úkolům Google. Zkontrolujte přihlašovací údaje a API v Google Cloud Console."

    if tasklist_name:
        tasklist_id = find_or_create_tasklist(service, tasklist_name)
        if not tasklist_id:
            return f"Chyba: Nepodařilo se najít ani vytvořit seznam '{tasklist_name}'."
    else:
        tasklist_id = '@default'

    task_body = {'title': title}
    if notes:
        task_body['notes'] = notes

    try:
        logger.info(f"Přidávám úkol '{title}' do seznamu id={tasklist_id}")
        service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        return f"Přidáno."
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        traceback.print_exc()
        return f"Chyba při vytváření úkolu: {e}"


def add_tasks_bulk(items: list[str], tasklist_name: str) -> str:
    """
    Adds multiple tasks at once to a named task list (creating it if needed).
    Returns a summary string.
    """
    service = get_tasks_service()
    if not service:
        return "Nelze se připojit k Úkolům Google."

    tasklist_id = find_or_create_tasklist(service, tasklist_name)
    if not tasklist_id:
        return f"Chyba: Nepodařilo se najít ani vytvořit seznam '{tasklist_name}'."

    added = 0
    errors = 0
    for item in items:
        try:
            service.tasks().insert(tasklist=tasklist_id, body={'title': item}).execute()
            logger.info(f"  + {item}")
            added += 1
        except Exception as e:
            logger.error(f"Chyba při přidávání '{item}': {e}")
            errors += 1

    result = f"Hotovo. Do seznamu '{tasklist_name}' přidáno {added} položek."
    if errors:
        result += f" ({errors} chyb)"
    return result


def get_tasks(tasklist_name: str = "") -> list:
    """
    Fetches incomplete tasks from a given Google Tasks list.
    If no name provided, fetches from the default list.
    """
    service = get_tasks_service()
    if not service:
        logger.error("get_tasks(): Nelze se připojit k Google Tasks.")
        return []

    if tasklist_name:
        tasklist_id = find_or_create_tasklist(service, tasklist_name)
        if not tasklist_id:
            logger.error(f"get_tasks(): Seznam '{tasklist_name}' nenalezen.")
            return []
    else:
        tasklist_id = '@default'

    try:
        results = service.tasks().list(tasklist=tasklist_id, showCompleted=False, showHidden=False).execute()
        items = results.get('items', [])
        
        tasks_list = []
        for item in items:
            tasks_list.append({
                "id": item['id'],
                "title": item['title'],
                "notes": item.get('notes', ''),
                "due": item.get('due', '')
            })
            
        return tasks_list
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        traceback.print_exc()
        return []


if __name__ == '__main__':
    import sys

    KROUZKY_ITEMS = [
        "Jachting Max",
        "Jachting Avi",
        "Jachting Beatrix",
        "Jachting České budějovice",
        "Regaty Max",
        "Regaty CR",
        "Záhrobsky tréninky",
        "Beatrix Polysport",
        "Beatrix balet",
        "Beatrix koníčky",
        "Avi Unihokej trénink",
        "Avi Unihokej zápasy",
        "Avi Unihokej Helfer",
        "Atletika Max",
        "Atletika Avi",
        "Atletika závody",
        "Avi Šachy",
        "Beatrix Pfadi Bülach",
        "Avi, Max Pfadi Embrach Schnupper",
        "Max plavání 1,5 hodinný",
        "Max Sprachaufenthalt",
        "Letní tábory",
        "Skaut Avi Cyril",
        "Skaut Beatrix Dorinka",
        "Housle Beatrix Jerie",
        "Beatrix Sbor Dragana (Felicita) Feld – středa odpoledne",
        "Avi angličtina",
        "Beatrix angličtina",
        "Soustředění Jachting Černá v Pošumaví 1.–3. května",
        "Max Itálie v dubnu – data?",
        "Léto Švédsko, road movie",
        "Velikonoce Stubai – Joker Tag",
        "Velikonoce Ledovec",
        "Max taneční a plesy",
        "Koncert Kloten – přeložit",
        "Koncert Hitmakers – noty a zkoušky",
    ]

    print("Vytvářím seznam 'Kroužky' a přidávám položky...")
    result = add_tasks_bulk(KROUZKY_ITEMS, "Kroužky")
    print(str(result).encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
