from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import uuid
import datetime
import os

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
        return redirect(url_for('chat_route', chat_id=new_chat_id))
    
    conn = get_db_connection()
    chats = conn.execute('SELECT DISTINCT chatid FROM chatlog').fetchall()
    conn.close()
    return render_template('index.html', chats=chats)

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
        
        # Simulate a system response (optional, but good for demo)
        # For now, just echo or acknowledge
        # conn.execute('INSERT INTO chatlog (chatid, message, timestamp, sender) VALUES (?, ?, ?, ?)',
        #              (chat_id, "Received: " + message, timestamp, 'System'))
        # conn.commit()
        
    messages = conn.execute('SELECT * FROM chatlog WHERE chatid = ? ORDER BY timestamp', (chat_id,)).fetchall()
    conn.close()
    
    return render_template('chat.html', chat_id=chat_id, messages=messages)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
