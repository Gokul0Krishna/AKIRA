from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import pandas as pd
import pandasql as ps

load_dotenv()

SPREADSHEET_ID = os.getenv('FORM_RESPONSES_SHEET')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

COLUMN_NAMES = ["submission_id", "srn", "request_type", "timestamp", "status"]

def post_latest_event():
    creds = Credentials.from_authorized_user_file("v3/token.json", SCOPES)
    service = build("sheets", "v4", credentials=creds)
    sheet_name = 'Form responses 1'
    range_name = f'{sheet_name}!A1:K100'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()
    values = result.get("values", [])
    print(f"ead {len(values)} rows from '{sheet_name}'")
    headers = values[0]
    data_rows = values[1:]
    headers
    data_rows
    df = pd.DataFrame(data=data_rows,columns=headers)
    latest_row = df.iloc[-1]  # last row
    srn = latest_row.get('SRN', '')
    tor = latest_row.get('The type of request', '')
    time = latest_row.get('Timestamp', '')

    # --- Prepare data for writing ---
    dest_sheet_name = 'procces tracker'
    write_range = f"{dest_sheet_name}!A1"

    row_to_write = [[f"{srn}-{tor}-{time}", srn, tor, time, "created"]]

    body = {"values": row_to_write}

    # --- Append to destination sheet ---
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=SPREADSHEET_ID,
            range=write_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        )
        .execute()
    )

def read_and_send():
    creds = Credentials.from_authorized_user_file("v3/token.json", SCOPES)
    service = build("sheets", "v4", credentials=creds)
    sheet_name = 'procces tracker'
    range_name = f'{sheet_name}!A1:K100'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()
    values = result.get("values", [])
    print(f"ead {len(values)} rows from '{sheet_name}'")
    data_rows = values[0:]
    df = pd.DataFrame(data_rows, columns=COLUMN_NAMES)
    query = """
    SELECT DISTINCT submission_id
    FROM df
    GROUP BY submission_id
    HAVING COUNT(DISTINCT status) = 1
    AND MAX(status) = 'created'
    """
    result = ps.sqldf(query)
    if result:
        for i in result:
            print('send email')


if __name__ == '__main__':
    post_latest_event()
    read_and_send()