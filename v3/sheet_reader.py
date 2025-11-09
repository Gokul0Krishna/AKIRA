from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os

load_dotenv()

SPREADSHEET_ID = os.getenv('FORM_RESPONSES_SHEET')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def read_form_responses():
    creds = Credentials.from_authorized_user_file('v3/token.json', SCOPES)
    service = build('sheets', 'v4', credentials=creds)
    sheet_name = 'Form responses 1'
    range_name = f'{sheet_name}!A1:K100'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()
    
    values = result.get('values', [])
    if values:
        print(f"Found {len(values)} rows (including header)")
        headers = values[0]
    print("\nHeaders:", headers)
    
    # Print each response
    for idx, row in enumerate(values[1:], start=2):
        print(f"\n--- Row {idx} ---")
        for i, header in enumerate(headers):
            value = row[i] if i < len(row) else "(empty)"
            print(f"  {header}: {value}")

    else:
        print('sheet empty')

if __name__ == "__main__":
    read_form_responses()
