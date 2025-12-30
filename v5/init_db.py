import sqlite3
import os

# Define the database file path
db_path = 'database'

# Connect to the database (this will create it if it doesn't exist)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create the chatlog table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS chatlog (
        chatid TEXT,
        message TEXT,
        timestamp TEXT,
        sender TEXT,
        workflow_generated BOOLEAN DEFAULT FALSE
    )
''')

# Create the state table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS state (
        chatid TEXT,
        workflow TEXT,
        version TEXT,
        timestamp TEXT
    )
''')

print("Database 'database' created/connected successfully.")
print("Tables 'chatlog' and 'state' ensured.")

conn.commit()
conn.close()
