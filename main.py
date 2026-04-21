from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import threading
import time
import random
import traceback
import re

app = Flask(__name__)

# --- Global State & Threading ---
bot_state = {
    "username": "",
    "sessionid": "",
    "urls": [],
    "comments": [],
    "proxies": [],
    "status": "Stopped",
    "logs": [],
    "data_bytes_used": 0  # Tracks data usage
}

stop_event = threading.Event()
bot_thread = None

def add_log(message):
    print(message)
    bot_state["logs"].insert(0, f"{time.strftime('%H:%M:%S')} - {message}")
    if len(bot_state["logs"]) > 50:
        bot_state["logs"].pop()

def format_bytes(size):
    """Converts bytes to KB or MB for easy reading"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

def data_tracker_hook(r, *args, **kwargs):
    """Intercepts Instagram requests to calculate proxy data usage"""
    try:
        # Calculate size of the outgoing request
        req_size = len(r.request.url) + len(str(r.request.headers))
        if r.request.body:
            req_size += len(r.request.body)
            
        # Calculate size of the incoming response
        res_size = len(str(r.headers)) + len(r.content)
        
        total_action_data = req_size + res_size
        bot_state["data_bytes_used"] += total_action_data
    except Exception:
        pass

def get_id_from_url_offline(url):
    """ZERO-DATA: Converts IG URL to Media ID using math instead of the proxy"""
    try:
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9\-_]+)", url)
        if not match:
            return url if url.isdigit() else None
        
        shortcode = match.group(1)
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        media_pk = 0
        for char in shortcode:
            media_pk = (media_pk * 64) + alphabet.index(char)
        return str(media_pk)
    except Exception:
        return None

def format_proxy(raw_proxy):
    try:
        # Clean the string from any whitespace or 'socks5://' prefixes
        clean_px = raw_proxy.strip().replace("socks5://", "").replace("http://", "")
        parts = clean_px.split(":")
        
        # If it's Host:Port:User:Pass
        if len(parts) == 4:
            return f"socks5://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return raw_proxy
    except:
        return None

def commenting_worker():
    add_log("Bot started in Low-Data Mode.")
    bot_state["status"] = "Running"
    
    cl = Client()
    
    # 1. LOW DATA SETTING: Disable background sync
    cl.is_sync_enabled = False 
    
    # 2. ATTACH DATA TRACKER: Count every byte sent/received
    cl.private.hooks['response'].append(data_tracker_hook)
    cl.public.hooks['response'].append(data_tracker_hook)

    login_successful = False

    while not stop_event.is_set():
        try:
            # Setup Proxy
            if bot_state["proxies"]:
                raw_proxy = random.choice(bot_state["proxies"])
                formatted_proxy = format_proxy(raw_proxy)
                if formatted_proxy:
                    cl.set_proxy(formatted_proxy)
                    add_log(f"Using Proxy: {formatted_proxy.split('@')[-1]}")

            # Session ID Login
            if not login_successful:
                add_log(f"Logging in with Session ID...")
                clean_session = bot_state["sessionid"].replace("\n", "").replace(" ", "").strip()
                cl.login_by_sessionid(clean_session)
                login_successful = True
                add_log("Session Login Successful!")

            # Process URLs
            for url in bot_state["urls"]:
                if stop_event.is_set():
                    break
                
                # 3. LOW DATA SETTING: Offline Math ID calculation
                media_id = get_id_from_url_offline(url)
                if not media_id:
                    add_log(f"Skipping invalid URL: {url}")
                    continue

                comment = random.choice(bot_state["comments"])
                add_log(f"Targeting Offline ID: {media_id}")
                
                # Start tracking data just for this comment
                data_before = bot_state["data_bytes_used"]
                
                try:
                    cl.media_comment(media_id, comment)
                    
                    data_used_this_action = bot_state["data_bytes_used"] - data_before
                    add_log(f"SUCCESS: Commented '{comment}' | Data Used: {format_bytes(data_used_this_action)}")
                except Exception as e:
                    add_log(f"FAILED on {url} - {str(e)[:50]}")

                # Safe Delay
                delay = random.randint(250, 300)
                add_log(f"Sleeping for {delay} seconds...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            add_log("Finished URL loop. Restarting in 30s...")
            time.sleep(30)

        except Exception as e:
            add_log(f"CRITICAL ERROR: {str(e)[:100]}")
            login_successful = False # Force login check
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
    <title>SMM Auto-Comment Pro</title>
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
        .data-badge { background-color: #17a2b8; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; }
    </style>
</head>
<body class="container">
    <h2 class="mb-4 text-center text-info fw-bold">SMM Auto-Comment (Low Data Mode)</h2>
    
    <div class="row">
        <div class="col-lg-6 mb-4">
            <div class="card p-4">
                <h4 class="mb-3 text-light">Configuration</h4>
                <form id="configForm">
                    <div class="row mb-3">
                        <div class="col-4">
                            <label class="form-label text-secondary small mb-1">IG Username</label>
                            <input type="text" id="username" class="form-control" required>
                        </div>
                        <div class="col-8">
                            <label class="form-label text-warning small mb-1">IG Session ID</label>
                            <input type="password" id="sessionid" class="form-control" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">Video URLs</label>
                        <textarea id="urls" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">Comments</label>
                        <textarea id="comments" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-secondary small mb-1">SOCKS5 Proxies (90m Rotation)</label>
                        <textarea id="proxies" class="form-control" rows="3" placeholder="Agreement://Host IP:Port:User:Pass"></textarea>
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
                    <h4 class="m-0 text-light">Live Dashboard</h4>
                    <div>
                        <span id="dataBadge" class="data-badge me-2">Data: 0 KB</span>
                        <span id="statusBadge" class="badge bg-secondary fs-6">Stopped</span>
                    </div>
                </div>
                <hr class="mt-0">
                <div id="logBox" class="log-box"></div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('configForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                username: document.getElementById('username').value,
                sessionid: document.getElementById('sessionid').value,
                urls: document.getElementById('urls').value.split('\\n').filter(u => u.trim()),
                comments: document.getElementById('comments').value.split('\\n').filter(c => c.trim()),
                proxies: document.getElementById('proxies').value.split('\\n').filter(p => p.trim())
            };
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            alert('Saved! Ready to Start.');
        });

        async function startBot() { await fetch('/api/start', {method: 'POST'}); updateUI(); }
        async function stopBot() { await fetch('/api/stop', {method: 'POST'}); updateUI(); }

        async function updateUI() {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            const statusBadge = document.getElementById('statusBadge');
            statusBadge.innerText = data.status;
            statusBadge.className = 'badge fs-6 ' + (data.status === 'Running' ? 'bg-success' : 'bg-danger');

            document.getElementById('dataBadge').innerText = 'Data: ' + data.data_formatted;
            document.getElementById('logBox').innerHTML = data.logs.join('<br>');
        }

        setInterval(updateUI, 2000);
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
    bot_state["sessionid"] = data.get("sessionid", "")
    bot_state["urls"] = data.get("urls", [])
    bot_state["comments"] = data.get("comments", [])
    bot_state["proxies"] = data.get("proxies", [])
    return jsonify({"success": True})

@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_thread
    if bot_state["status"] == "Running":
        return jsonify({"error": "Already running"})
    
    stop_event.clear()
    bot_thread = threading.Thread(target=commenting_worker)
    bot_thread.daemon = True
    bot_thread.start()
    return jsonify({"success": True})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    if bot_state["status"] == "Running":
        stop_event.set()
        add_log("Stopping bot after current task...")
    return jsonify({"success": True})

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "status": bot_state["status"],
        "logs": bot_state["logs"],
        "data_formatted": format_bytes(bot_state["data_bytes_used"])
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
