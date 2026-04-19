from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import threading
import time
import random
import traceback
import os

app = Flask(__name__)

# --- Global State & Threading ---
bot_state = {
    "username": "",
    "password": "",
    "urls": [],
    "comments": [],
    "proxies": [],
    "status": "Stopped",
    "logs": []
}

stop_event = threading.Event()
bot_thread = None

def add_log(message):
    print(message)
    bot_state["logs"].insert(0, f"{time.strftime('%H:%M:%S')} - {message}")
    # Keep only the last 50 logs in memory to prevent slowing down the browser
    if len(bot_state["logs"]) > 50:
        bot_state["logs"].pop()

def format_proxy(raw_proxy):
    """Converts OwlProxy format to standard Requests SOCKS5 format"""
    try:
        raw_proxy = raw_proxy.strip()
        if not raw_proxy: return None
        
        if "://" in raw_proxy:
            rest = raw_proxy.split("://")[1]
        else:
            rest = raw_proxy
            
        parts = rest.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            # Strictly use SOCKS5 protocol
            return f"socks5://{user}:{password}@{host}:{port}"
        
        return raw_proxy
    except Exception as e:
        add_log(f"Proxy Parse Error: {e}")
        return None

def commenting_worker():
    add_log("Bot thread started.")
    bot_state["status"] = "Running"
    
    cl = Client()
    login_successful = False
    
    # Create a unique session file name for this account
    session_file = f"session_{bot_state['username']}.json"

    while not stop_event.is_set():
        try:
            # 1. Select a random proxy and apply it
            if bot_state["proxies"]:
                raw_proxy = random.choice(bot_state["proxies"])
                formatted_proxy = format_proxy(raw_proxy)
                
                if formatted_proxy:
                    cl.set_proxy(formatted_proxy)
                    safe_log_proxy = formatted_proxy.split('@')[-1]
                    add_log(f"Using Proxy: {safe_log_proxy}")

            # 2. Login Logic (With Session Saving)
            if not login_successful:
                if os.path.exists(session_file):
                    add_log("Found existing session file, attempting to load...")
                    cl.load_settings(session_file)
                    try:
                        # Test if the session is still valid
                        cl.get_timeline_feed()
                        login_successful = True
                        add_log("Logged in successfully using saved session cookie!")
                    except Exception:
                        add_log("Saved session expired or invalid. Re-logging in...")
                        login_successful = False

                if not login_successful:
                    add_log(f"Attempting fresh password login for {bot_state['username']}...")
                    cl.login(bot_state["username"], bot_state["password"])
                    cl.dump_settings(session_file) # Save session for next time
                    login_successful = True
                    add_log("Fresh login successful! Session saved.")

            # 3. Process URLs
            for url in bot_state["urls"]:
                if stop_event.is_set():
                    break
                
                comment = random.choice(bot_state["comments"])
                add_log(f"Targeting URL: {url}")
                
                try:
                    media_id = cl.media_id(cl.media_pk_from_url(url))
                    comment_obj = cl.media_comment(media_id, comment)
                    add_log(f"SUCCESS: Commented '{comment}' on {url}")
                except Exception as e:
                    add_log(f"FAILED on {url} - {str(e)[:100]}")

                # Anti-Ban Delay (30 to 60 seconds)
                delay = random.randint(30, 60)
                add_log(f"Sleeping for {delay} seconds to prevent ban...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            add_log("Finished loop through all URLs. Restarting in 10s...")
            time.sleep(10)

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            add_log(f"CRITICAL ERROR: {error_msg[:150]}")
            add_log("Cooling down for 60 seconds before retrying...")
            
            login_successful = False # Force a re-login check on next loop
            
            # Delete corrupted session file if Instagram blocked the session
            if "challenge" in error_msg.lower() or "blacklist" in error_msg.lower() or "login" in error_msg.lower():
                 if os.path.exists(session_file):
                     os.remove(session_file)
                     add_log("Deleted invalid session file. Will perform fresh login next cycle.")
                     
            for _ in range(60):
                if stop_event.is_set(): break
                time.sleep(1)

    bot_state["status"] = "Stopped"
    add_log("Bot thread stopped.")


# --- Web Routes & HTML ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMM Auto-Comment Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; }
        .log-box { 
            height: 350px; 
            overflow-y: scroll; 
            background: #0d1117; 
            padding: 15px; 
            font-family: 'Courier New', Courier, monospace; 
            color: #00ff00; 
            border-radius: 8px; 
            border: 1px solid #30363d;
            font-size: 14px;
        }
        textarea { font-family: monospace; }
        .card { box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    </style>
</head>
<body class="container">
    <h2 class="mb-4 text-center text-info fw-bold">SMM Comment Automation</h2>
    
    <div class="row">
        <div class="col-lg-6 mb-4">
            <div class="card p-4">
                <h4 class="mb-3 text-light">Configuration</h4>
                <form id="configForm">
                    <div class="row mb-3">
                        <div class="col">
                            <label class="form-label text-secondary small mb-1">IG Username</label>
                            <input type="text" id="username" class="form-control" required>
                        </div>
                        <div class="col">
                            <label class="form-label text-secondary small mb-1">IG Password</label>
                            <input type="password" id="password" class="form-control" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">Video URLs (One per line)</label>
                        <textarea id="urls" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">Comments (One per line)</label>
                        <textarea id="comments" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">SOCKS5 Proxies (One per line)</label>
                        <textarea id="proxies" class="form-control" rows="3" placeholder="socks5://change4.owlproxy.com..."></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 mb-3 fw-bold">Save Configuration</button>
                </form>
                
                <div class="d-flex gap-2">
                    <button onclick="startBot()" class="btn btn-success flex-grow-1 fw-bold py-2">START BOT</button>
                    <button onclick="stopBot()" class="btn btn-danger flex-grow-1 fw-bold py-2">STOP BOT</button>
                </div>
            </div>
        </div>

        <div class="col-lg-6">
            <div class="card p-4 h-100">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h4 class="m-0 text-light">Status Dashboard</h4>
                    <span id="statusBadge" class="badge bg-secondary fs-6">Stopped</span>
                </div>
                <hr class="mt-0">
                <h5 class="text-secondary mb-3">Live Terminal</h5>
                <div id="logBox" class="log-box"></div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('configForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                username: document.getElementById('username').value,
                password: document.getElementById('password').value,
                urls: document.getElementById('urls').value.split('\\n').filter(u => u.trim()),
                comments: document.getElementById('comments').value.split('\\n').filter(c => c.trim()),
                proxies: document.getElementById('proxies').value.split('\\n').filter(p => p.trim())
            };
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            alert('Configuration Saved To Memory!');
        });

        async function startBot() {
            await fetch('/api/start', {method: 'POST'});
            updateUI();
        }

        async function stopBot() {
            await fetch('/api/stop', {method: 'POST'});
            updateUI();
        }

        async function updateUI() {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            const badge = document.getElementById('statusBadge');
            badge.innerText = data.status;
            
            // Update badge color based on status
            badge.className = 'badge fs-6 ' + (data.status === 'Running' ? 'bg-success' : 'bg-danger');

            const logBox = document.getElementById('logBox');
            logBox.innerHTML = data.logs.join('<br>');
        }

        setInterval(updateUI, 2000); // Auto-refresh logs every 2 seconds
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.json
    bot_state["username"] = data.get("username", "")
    bot_state["password"] = data.get("password", "")
    bot_state["urls"] = data.get("urls", [])
    bot_state["comments"] = data.get("comments", [])
    bot_state["proxies"] = data.get("proxies", [])
    return jsonify({"success": True})

@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_thread
    if bot_state["status"] == "Running":
        return jsonify({"error": "Already running"})
    
    if not bot_state["username"] or not bot_state["urls"] or not bot_state["comments"]:
        return jsonify({"error": "Missing configuration"})

    stop_event.clear()
    bot_thread = threading.Thread(target=commenting_worker)
    bot_thread.daemon = True
    bot_thread.start()
    return jsonify({"success": True})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    if bot_state["status"] == "Running":
        stop_event.set()
        add_log("Stop signal sent. Waiting for current task to finish...")
    return jsonify({"success": True})

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "status": bot_state["status"],
        "logs": bot_state["logs"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
