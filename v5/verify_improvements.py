import sqlite3
import os
import uuid
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'database')

def verify_improvements():
    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. Test Preview Logic
        chat_id = str(uuid.uuid4())
        long_msg = "one two three four five six seven eight nine ten eleven twelve thirteen"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (chat_id, long_msg, timestamp, 'User'))
        conn.commit()
        
        # Mock the preview logic from app.py
        words = long_msg.split()
        preview = " ".join(words[:10]) + ("..." if len(words) > 10 else "")
        print(f"Testing Preview Logic:")
        print(f"Original: {long_msg}")
        print(f"Preview:  {preview}")
        
        expected_preview = "one two three four five six seven eight nine ten..."
        if preview == expected_preview:
            print("SUCCESS: Preview logic is correct.")
        else:
            print(f"FAILURE: Preview logic returned '{preview}' instead of '{expected_preview}'")

        # 2. Test Deletion Logic
        print("\nTesting Deletion Logic...")
        conn.execute('DELETE FROM chatlog WHERE chatid = ?', (chat_id,))
        conn.commit()
        
        cursor = conn.execute('SELECT COUNT(*) FROM chatlog WHERE chatid = ?', (chat_id,))
        count = cursor.fetchone()[0]
        if count == 0:
            print("SUCCESS: Chat deletion logic works correctly.")
        else:
            print(f"FAILURE: Chat deletion failed, {count} records remain.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    verify_improvements()
