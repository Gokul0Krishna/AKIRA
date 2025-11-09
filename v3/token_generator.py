"""
Test script to authenticate with Google APIs
This will open a browser and ask for permissions
"""

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

# Scopes - what permissions we need
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file'
]

def authenticate():
    """Authenticate and save token"""
    creds = None
    
    # Check if token.json exists (already authenticated)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("Starting authentication flow...")
            print("A browser window will open. Please sign in and grant permissions.")
            flow = InstalledAppFlow.from_client_secrets_file('v3/credentials.json       ', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        print("Authentication successful! token.json saved.")
    else:
        print("Already authenticated. Using existing token.json")
    
    return creds

def test_sheets_access():
    """Test if we can read Google Sheets"""
    creds = authenticate()
    
    from dotenv import load_dotenv
    load_dotenv()
    
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    
    if not spreadsheet_id:
        print("ERROR: SPREADSHEET_ID not found in .env file")
        return
    
    print(f"\nTesting access to spreadsheet: {spreadsheet_id}")
    
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    # Try to read sheet names
    result = sheet.get(spreadsheetId=spreadsheet_id).execute()
    sheets = result.get('sheets', [])
    
    print("\n✓ Successfully connected to Google Sheets!")
    print(f"Found {len(sheets)} sheets:")
    for s in sheets:
        print(f"  - {s['properties']['title']}")

if __name__ == "__main__":
    print("=" * 50)
    print("GOOGLE API AUTHENTICATION TEST")
    print("=" * 50)
    test_sheets_access()