import sqlite3
import os

# Define the database file path
db_path = os.path.join(os.path.dirname(__file__), 'database')

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create the state table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS state (
        chatid TEXT,
        workflow TEXT,
        version TEXT,
        timestamp TEXT
    )
''')

print("Table 'state' ensured in the database.")

conn.commit()
conn.close()
