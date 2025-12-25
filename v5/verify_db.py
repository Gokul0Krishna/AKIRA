import sqlite3
import os

db_path = 'database'

if not os.path.exists(db_path):
    print(f"Error: {db_path} does not exist.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Checking database at {os.path.abspath(db_path)}")

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chatlog';")
table = cursor.fetchone()
print(f"Table 'chatlog' exists: {table is not None}")

if table:
    # Check columns
    cursor.execute("PRAGMA table_info(chatlog);")
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")

conn.close()
