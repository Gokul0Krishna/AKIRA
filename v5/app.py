from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import uuid
import datetime
import os
from agent import WorkflowAgent

# Initialize the agent
agent = WorkflowAgent()

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'database')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Start a new chat
        new_chat_id = str(uuid.uuid4())
        
        # Insert initial greeting
        conn = get_db_connection()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (new_chat_id, "what are we building today?", timestamp, 'System'))
        conn.commit()
        conn.close()
        
        return redirect(url_for('chat_route', chat_id=new_chat_id))
    
    conn = get_db_connection()
    # Get the latest message for each chatid
    query = '''
        SELECT c1.chatid, c1.message 
        FROM chatlog c1
        JOIN (
            SELECT chatid, MAX(timestamp) as max_ts
            FROM chatlog
            GROUP BY chatid
        ) c2 ON c1.chatid = c2.chatid AND c1.timestamp = c2.max_ts
    '''
    chats_raw = conn.execute(query).fetchall()
    conn.close()
    
    chats = []
    for chat in chats_raw:
        msg = chat['message'] or ""
        words = msg.split()
        preview = " ".join(words[:10]) + ("..." if len(words) > 10 else "")
        chats.append({
            'chatid': chat['chatid'],
            'preview': preview or f"Chat {chat['chatid'][:8]}"
        })
        
    return render_template('index.html', chats=chats)

@app.route('/delete/<chat_id>', methods=['POST'])
def delete_chat(chat_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM chatlog WHERE chatid = ?', (chat_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/<chat_id>', methods=['GET', 'POST'])
def chat_route(chat_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        message = request.form['message']
        sender = 'User' # Hardcoded for now, could be dynamic
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (chat_id, message, timestamp, sender))
        conn.commit()
        
        # Get response from agent
        try:
            response_text = agent.run_step(message, chat_id)
        except Exception as e:
            response_text = f"Error processing request: {str(e)}"
            
        # Save system response
        sys_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
                     (chat_id, response_text, sys_timestamp, 'System'))
        conn.commit()
        
    messages = conn.execute('SELECT * FROM chatlog WHERE chatid = ? ORDER BY timestamp', (chat_id,)).fetchall()
    conn.close()
    
    return render_template('chat.html', chat_id=chat_id, messages=messages)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
