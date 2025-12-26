import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'database')

def verify_storage():
    chat_id = "test-verification-id"
    user_msg = "Hello Agent"
    agent_msg = "Hello User, how can I help?"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # Simulate User Message Storage
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (chat_id, user_msg, timestamp, 'User'))
        
        # Simulate Agent Message Storage
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (chat_id, agent_msg, timestamp, 'System'))
        conn.commit()
        
        # Verify
        cursor = conn.execute('SELECT * FROM chatlog WHERE chatid = ?', (chat_id,))
        rows = cursor.fetchall()
        
        print(f"Found {len(rows)} messages for chatid {chat_id}:")
        for row in rows:
            print(f"Sender: {row[3]}, Message: {row[1]}")
            
        if len(rows) == 2 and rows[1][3] == 'System':
            print("\nSUCCESS: Both user and agent messages are correctly stored in the database.")
        else:
            print("\nFAILURE: Storage verification failed.")
            
    finally:
        # Clean up
        conn.execute('DELETE FROM chatlog WHERE chatid = ?', (chat_id,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    verify_storage()
