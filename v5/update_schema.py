import sqlite3

db_path = 'database'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE chatlog ADD COLUMN sender TEXT;")
    print("Column 'sender' added successfully.")
except sqlite3.OperationalError as e:
    print(f"Operation failed (column might already exist): {e}")

conn.commit()
conn.close()
