import sqlite3

db_path = 'database'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE chatlog ADD COLUMN workflow_generated BOOLEAN DEFAULT FALSE;")
    print("Column 'workflow_generated' added successfully.")
except sqlite3.OperationalError as e:
    print(f"Operation failed (column might already exist): {e}")

conn.commit()
conn.close()
