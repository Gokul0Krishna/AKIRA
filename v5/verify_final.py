from agent import WorkflowAgent
import sqlite3
import os
import uuid
import json

DB_PATH = os.path.join(os.path.dirname(__file__), 'database')

def verify_final_persistence():
    print("Testing Final Workflow Persistence and DB Status...")
    agent = WorkflowAgent()
    chat_id = "test_persistence_" + str(uuid.uuid4())[:8]
    
    # 1. Simulate the insertion of the user message (should be False)
    conn = sqlite3.connect(DB_PATH)
    try:
        # Mocking the app.py logic for user message
        workflow_exists = os.path.exists(f"{chat_id}.json")
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender, workflow_generated) VALUES (?, ?, ?, ?, ?)',
                     (chat_id, "Build a simple request", "2023-01-01 10:00:00", 'User', workflow_exists))
        conn.commit()
        
        # 2. Mock Agent Completion (manually calling _display_output)
        mock_state = {
            "master_json": {"metadata": {"workflow_name": "Test", "description": "Test"}},
            "chat_id": chat_id
        }
        print(f"Executing _display_output for {chat_id}")
        resp = agent._display_output(mock_state)
        
        # 3. Simulate System Response insertion (should be True)
        workflow_exists = os.path.exists(f"{chat_id}.json")
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender, workflow_generated) VALUES (?, ?, ?, ?, ?)',
                     (chat_id, resp['last_message'], "2023-01-01 10:00:01", 'System', workflow_exists))
        conn.commit()
        
        # 4. Verify DB Status
        cursor = conn.execute('SELECT workflow_generated, sender FROM chatlog WHERE chatid = ? ORDER BY timestamp', (chat_id,))
        rows = cursor.fetchall()
        
        print("\nDB Records for current chat:")
        for r in rows:
            print(f"Sender: {r[1]}, workflow_generated: {r[0]}")
            
        if rows[0][0] == 0 and rows[1][0] == 1:
            print("\nSUCCESS: Database status correctly toggled on completion.")
        else:
            print("\nFAILURE: Database status did not update correctly.")
            
        # 5. Check if file exists
        if os.path.exists(f"{chat_id}.json"):
            print(f"SUCCESS: File {chat_id}.json was created.")
        else:
            print(f"FAILURE: File {chat_id}.json was NOT created.")
            
    finally:
        # Cleanup
        if os.path.exists(f"{chat_id}.json"):
            os.remove(f"{chat_id}.json")
        conn.execute('DELETE FROM chatlog WHERE chatid = ?', (chat_id,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    verify_final_persistence()
