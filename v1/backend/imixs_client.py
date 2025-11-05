import requests

IMIXS_URL = "http://localhost:8080/api/workflow/workitems"

def create_workitem(subject, applicant, data):
    payload = {
        "subject": subject,
        "applicant": applicant,
        "status": "submitted",
        "data": data
    }
    r = requests.post(IMIXS_URL, json=payload, auth=('admin', 'admin'))
    r.raise_for_status()
    return r.json()

def update_workitem(workitem_id, action):
    url = f"{IMIXS_URL}/{workitem_id}"
    payload = {"action": action}
    r = requests.put(url, json=payload, auth=('admin', 'admin'))
    r.raise_for_status()
    return r.json()
