import requests
import multiprocessing
import time
import sys
from app import app
import os
import signal

# Function to run the Flask app
def run_app():
    # Suppress flask output
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    app.run(port=5001)

if __name__ == '__main__':
    # Start the app in a separate process
    server_process = multiprocessing.Process(target=run_app)
    server_process.start()
    
    # Wait for the server to start
    time.sleep(2)
    
    try:
        base_url = 'http://127.0.0.1:5001'
        
        # Test Home Page
        print("Testing Home Page...")
        resp = requests.get(base_url)
        if resp.status_code == 200:
            print("Home Page: OK")
        else:
            print(f"Home Page: FAILED ({resp.status_code})")
            
        # Test New Chat Creation (Redirect)
        print("Testing New Chat Creation...")
        resp = requests.post(base_url, allow_redirects=False)
        if resp.status_code == 302:
            new_chat_url = resp.headers['Location']
            print(f"New Chat Redirect: OK ({new_chat_url})")
            
            # Follow redirect
            resp = requests.get(base_url + new_chat_url)
            if resp.status_code == 200:
                print("Chat Page: OK")
            else:
                print(f"Chat Page: FAILED ({resp.status_code})")
        else:
             print(f"New Chat Redirect: FAILED ({resp.status_code})")

    except Exception as e:
        print(f"Verification Failed: {e}")
    finally:
        # Terminate the server process
        server_process.terminate()
        server_process.join()
