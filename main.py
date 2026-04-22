from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import threading
import time
import random
import traceback

app = Flask(__name__)

# --- Global State & Threading ---
bot_state = {
    "username": "",
    "sessionid": "",
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
    if len(bot_state["logs"]) > 50:
        bot_state["logs"].pop()

def format_proxy(raw_proxy):
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
            return f"socks5://{user}:{password}@{host}:{port}"
        return raw_proxy
    except Exception as e:
        add_log(f"Proxy Parse Error: {e}")
        return None

def commenting_worker():
    add_log("Bot thread started. Anti-Ban Mode Active.")
    bot_state["status"] = "Running"
    
    cl = Client()
    # Mask the bot as a standard Indian mobile device
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False # Stops unnecessary background data
    
    # ==========================================
    # 1. ONE-TIME SETUP (Outside the Loop)
    # ==========================================
    
    # Set the Proxy ONCE. It will not switch IPs and trigger flags.
    if bot_state["proxies"]:
        formatted_proxy = format_proxy(bot_state["proxies"][0]) # Always uses the FIRST proxy line
        if formatted_proxy:
            cl.set_proxy(formatted_proxy)
            add_log(f"Locked to single proxy: {formatted_proxy.split('@')[-1]}")

    # Set the Session ID ONCE. 
    try:
        add_log("Loading Session ID...")
        clean_session = bot_state["sessionid"].replace("\n", "").replace(" ", "").strip()
        cl.login_by_sessionid(clean_session)
        add_log("Session loaded successfully. Starting comments...")
    except Exception as e:
        add_log(f"CRITICAL: Failed to load session: {str(e)[:50]}")
        bot_state["status"] = "Stopped"
        return

    # ==========================================
    # 2. COMMENTING LOOP
    # ==========================================
    while not stop_event.is_set():
        try:
            for url in bot_state["urls"]:
                if stop_event.is_set():
                    break
                
                comment = random.choice(bot_state["comments"])
                
                try:
                    media_id = cl.media_id(cl.media_pk_from_url(url))
                    cl.media_comment(media_id, comment)
                    add_log(f"SUCCESS: Commented '{comment}' on {url[-15:]}")
                except Exception as e:
                    error_msg = str(e).lower()
                    add_log(f"FAILED on url - {error_msg[:50]}")
                    
                    # EMERGENCY BRAKE: Stop immediately if IG asks for verification
                    if "checkpoint" in error_msg or "challenge" in error_msg or "login_required" in error_msg or "feedback_required" in error_msg:
                        add_log("SECURITY ALERT: Stopping bot to prevent account ban.")
                        bot_state["status"] = "Stopped"
                        stop_event.set()
                        break

                # HUMAN DELAY: 3 to 6 minutes between comments
                delay = random.randint(180, 360)
                add_log(f"Sleeping for {delay // 60}m {delay % 60}s to prevent ban...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            if not stop_event.is_set():
                add_log("Finished list. Resting for 10 minutes before restarting list...")
                time.sleep(600)

        except Exception as e:
            add_log(f"SYSTEM ERROR: {str(e)[:100]}")
            add_log("Pausing for 2 minutes. Will NOT re-login.")
            time.sleep(120)

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
    <h2 class="mb-4 text-center text-info fw-bold">SMM Comment Automation (Anti-Ban)</h2>
    
    <div class="row">
        <div class="col-lg-6 mb-4">
            <div class="card p-4">
                <h4 class="mb-3 text-light">Configuration</h4>
                <form id="configForm">
                    <div class="row mb-3">
                        <div class="col-4">
                            <label class="form-label text-secondary small mb-1">IG Username</label>
                            <input type="text" id="username" class="form-control" placeholder="username" required>
                        </div>
                        <div class="col-8">
                            <label class="form-label text-warning small mb-1">IG Session ID (Cookie)</label>
                            <input type="password" id="sessionid" class="form-control" placeholder="Paste long session cookie here..." required>
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
                        <label class="form-label text-secondary small mb-1">SOCKS5 Proxy (Bot uses ONLY the 1st line)</label>
                        <textarea id="proxies" class="form-control" rows="2" placeholder="Agreement://Host IP:Port:Username:Password"></textarea>
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
            alert('Configuration Saved! Ready to Start.');
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
            badge.className = 'badge fs-6 ' + (data.status === 'Running' ? 'bg-success' : 'bg-danger');

            const logBox = document.getElementById('logBox');
            logBox.innerHTML = data.logs.join('<br>');
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
    
    if not bot_state["username"] or not bot_state["sessionid"] or not bot_state["urls"]:
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
