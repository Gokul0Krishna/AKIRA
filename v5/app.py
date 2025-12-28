from flask import Flask, render_template, request, redirect, url_for, Response, stream_with_context
import sqlite3
import uuid
import datetime
import os
import json
from agent import WorkflowAgent

# Initialize the agent
agent = WorkflowAgent()

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'database')
WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), 'workflows')
os.makedirs(WORKFLOWS_DIR, exist_ok=True)

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
        
        # Check if workflow exists
        workflow_exists = os.path.exists(os.path.join(WORKFLOWS_DIR, f"{new_chat_id}.json"))
        
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender, workflow_generated) VALUES (?, ?, ?, ?, ?)',
                     (new_chat_id, "what are we building today?", timestamp, 'System', workflow_exists))
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
        # Check if it's an AJAX request (JSON)
        if request.is_json:
            data = request.get_json()
            message = data.get('message', '')
        else:
            message = request.form.get('message', '')
            
        sender = 'User'
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if workflow exists
        workflow_exists = os.path.exists(os.path.join(WORKFLOWS_DIR, f"{chat_id}.json"))
        
        conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender, workflow_generated) VALUES (?, ?, ?, ?, ?)',
                     (chat_id, message, timestamp, sender, workflow_exists))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return {'status': 'success'}
        return redirect(url_for('chat_route', chat_id=chat_id))
        
    messages = conn.execute('SELECT * FROM chatlog WHERE chatid = ? ORDER BY timestamp', (chat_id,)).fetchall()
    conn.close()
    
    return render_template('chat.html', chat_id=chat_id, messages=messages)

@app.route('/stream/<chat_id>')
def stream(chat_id):
    # Get the last user message to process
    conn = get_db_connection()
    last_user_msg = conn.execute('SELECT message FROM chatlog WHERE chatid = ? AND sender = "User" ORDER BY timestamp DESC LIMIT 1', (chat_id,)).fetchone()
    conn.close()
    
    if not last_user_msg:
        return Response("No message to process", status=400)

    def generate():
        try:
            for update in agent.run_step_stream(last_user_msg['message'], chat_id):
                if isinstance(update, str):
                    # Progress update
                    yield f"data: {json.dumps({'type': 'log', 'content': update})}\n\n"
                elif isinstance(update, dict) and "final_message" in update:
                    # Final message
                    response_text = update['final_message']
                    sys_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Store in DB
                    conn_sys = get_db_connection()
                    workflow_exists = os.path.exists(os.path.join(WORKFLOWS_DIR, f"{chat_id}.json"))
                    conn_sys.execute('INSERT INTO chatlog (chatid, message, timestamp, sender, workflow_generated) VALUES (?, ?, ?, ?, ?)',
                                 (chat_id, response_text, sys_timestamp, 'System', workflow_exists))
                    conn_sys.commit()
                    conn_sys.close()
                    
                    yield f"data: {json.dumps({'type': 'final', 'content': response_text, 'timestamp': sys_timestamp, 'workflow_generated': workflow_exists})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/get_json/<chat_id>')
def get_json(chat_id):
    filepath = os.path.join(WORKFLOWS_DIR, f"{chat_id}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return json.dumps(data)
    return {'error': 'File not found'}, 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
