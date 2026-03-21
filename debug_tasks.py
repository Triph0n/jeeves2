import sys
sys.path.append('.')
from src.tasks_controller import get_tasks_service

service = get_tasks_service()
if not service:
    print("Can't connect to Tasks!")
    sys.exit(1)

# List all task lists
print("=== Task Lists ===")
tasklists = service.tasklists().list(maxResults=10).execute()
for tl in tasklists.get('items', []):
    print(f"  [{tl['id']}] {tl['title']}")
    # Show tasks in each list
    tasks = service.tasks().list(tasklist=tl['id'], maxResults=20).execute()
    for task in tasks.get('items', []):
        print(f"    - {task.get('title', '(no title)')}")
    if not tasks.get('items'):
        print("    (no tasks)")
