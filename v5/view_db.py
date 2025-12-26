import sqlite3
import os

def view_database():
    db_path = os.path.join(os.path.dirname(__file__), 'database')
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    if not tables:
        print("No tables found in the database.")
        conn.close()
        return

    for table_name in tables:
        table_name = table_name[0]
        print(f"\n{'='*80}")
        print(f" TABLE: {table_name}")
        print(f"{'='*80}")

        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Print headers
        header_fmt = " | ".join([f"{col:<20}" for col in columns])
        print(header_fmt)
        print("-" * len(header_fmt))

        # Get rows
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY chatid, timestamp;")
        rows = cursor.fetchall()
        
        for row in rows:
            row_str = []
            for item in row:
                # Truncate long messages for readability
                val = str(item).replace('\n', ' ')
                if len(val) > 50:
                    val = val[:47] + "..."
                row_str.append(f"{val:<20}")
            print(" | ".join(row_str))

    conn.close()

if __name__ == "__main__":
    view_database()
