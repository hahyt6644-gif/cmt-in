from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import urllib.parse
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
    "data_bytes_used": 0
}

stop_event = threading.Event()
bot_thread = None

def add_log(message):
    print(message)
    bot_state["logs"].insert(0, f"{time.strftime('%H:%M:%S')} - {message}")
    if len(bot_state["logs"]) > 50: bot_state["logs"].pop()

def format_bytes(size):
    if size < 1024: return f"{size} B"
    return f"{size / 1024:.2f} KB"

def data_tracker_hook(r, *args, **kwargs):
    """Tracks proxy data usage"""
    try:
        req = len(r.request.url) + len(str(r.request.headers)) + len(r.request.body or "")
        res = len(str(r.headers)) + len(r.content)
        bot_state["data_bytes_used"] += (req + res)
    except: pass

def get_id_offline(url):
    """Math conversion logic - 0 KB Proxy Data used"""
    try:
        if not url or not isinstance(url, str): return None
        clean_url = url.strip().split("?")[0]
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9\-_]+)", clean_url)
        if match: shortcode = match.group(1)
        else: return clean_url if clean_url.isdigit() else None
        
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        media_pk = 0
        for char in shortcode:
            media_pk = (media_pk * 64) + alphabet.index(char)
        return str(media_pk)
    except: return None

def format_proxy(raw_proxy):
    try:
        raw_proxy = raw_proxy.strip().replace("socks5://", "").replace("http://", "")
        if not raw_proxy: return None
        parts = raw_proxy.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"socks5://{user}:{password}@{host}:{port}"
        return raw_proxy
    except: return None

def commenting_worker():
    add_log("Bot thread started. Strict Anti-Ban Mode.")
    bot_state["status"] = "Running"
    
    cl = Client()
    # Mask the bot as a standard Indian mobile device
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False 
    
    cl.private.hooks['response'].append(data_tracker_hook)
    cl.public.hooks['response'].append(data_tracker_hook)
    
    # ==========================================
    # 1. SETUP PROXY ONCE
    # ==========================================
    if bot_state["proxies"]:
        active_proxy = format_proxy(bot_state["proxies"][0]) # Always lock to the 1st line
        if active_proxy:
            cl.set_proxy(active_proxy)
            add_log(f"Locked to proxy: {active_proxy.split('@')[-1]}")
            time.sleep(5) # Let connection stabilize

    # ==========================================
    # 2. SECURE LOGIN ONCE
    # ==========================================
    try:
        add_log("Authenticating Session ID...")
        clean_session = urllib.parse.unquote(bot_state["sessionid"]).replace(" ", "").replace("\n", "").strip()
        
        cl.login_by_sessionid(clean_session)
        time.sleep(3)
        cl.get_timeline_feed() # Test the connection
        add_log("SUCCESS: Session connected and healthy!")
        
    except Exception as e:
        err_msg = str(e).lower()
        if "none" in err_msg or "group" in err_msg or "login_required" in err_msg:
            add_log("CRITICAL: Your Session ID is DEAD or Blocked.")
            add_log("ACTION: Delete it and get a new one from your browser.")
        else:
            add_log(f"LOGIN FAILED: {err_msg[:50]}")
        
        bot_state["status"] = "Stopped"
        stop_event.set()
        return

    # ==========================================
    # 3. COMMENTING LOOP
    # ==========================================
    while not stop_event.is_set():
        try:
            for url in bot_state["urls"]:
                if stop_event.is_set(): break
                
                mid = get_id_offline(url)
                if not mid: continue
                
                comment = random.choice(bot_state["comments"])
                before_data = bot_state["data_bytes_used"]
                
                try:
                    cl.media_comment(mid, comment)
                    used = format_bytes(bot_state["data_bytes_used"] - before_data)
                    add_log(f"SUCCESS: Commented on {url[-15:]} | Used: {used}")
                except Exception as e:
                    error_msg = str(e).lower()
                    add_log(f"FAILED on URL - {error_msg[:40]}")
                    
                    # EMERGENCY BRAKE
                    if "checkpoint" in error_msg or "challenge" in error_msg or "feedback_required" in error_msg:
                        add_log("SECURITY ALERT: Bot stopped to prevent ban.")
                        bot_state["status"] = "Stopped"
                        stop_event.set()
                        return

                # HUMAN DELAY: 3 to 6 minutes
                delay = random.randint(180, 360)
                add_log(f"Resting for {delay // 60}m {delay % 60}s...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            if not stop_event.is_set():
                add_log("List complete. Waiting 10m before restarting...")
                time.sleep(600)

        except Exception as e:
            add_log(f"SYSTEM ERROR: {str(e)[:50]}")
            time.sleep(60)

    bot_state["status"] = "Stopped"


# --- Web UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMM Auto-Comment (Ban-Safe)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; }
        .log-box { height: 350px; overflow-y: scroll; background: #0d1117; padding: 15px; font-family: monospace; color: #0f0; border-radius: 8px; border: 1px solid #30363d; font-size: 13px; }
    </style>
</head>
<body class="container">
    <h3 class="mb-4 text-center text-info fw-bold">SMM Automation (Anti-Ban Mode)</h3>
    <div class="row">
        <div class="col-lg-6 mb-4">
            <div class="card p-4">
                <form id="configForm">
                    <label class="form-label text-warning small mb-1">Session ID (Cookie)</label>
                    <input type="password" id="sessionid" class="form-control mb-3" placeholder="Paste fresh session cookie..." required>
                    
                    <label class="form-label text-secondary small mb-1">Video URLs</label>
                    <textarea id="urls" class="form-control mb-3" rows="4" required></textarea>
                    
                    <label class="form-label text-secondary small mb-1">Comments</label>
                    <textarea id="comments" class="form-control mb-3" rows="3" required></textarea>
                    
                    <label class="form-label text-secondary small mb-1">SOCKS5 Proxy (Bot uses ONLY 1st line)</label>
                    <textarea id="proxies" class="form-control mb-3" rows="2" placeholder="Host:Port:User:Pass"></textarea>
                    
                    <button type="submit" class="btn btn-primary w-100 mb-3 fw-bold">Save Configuration</button>
                </form>
                <div class="d-flex gap-2">
                    <button onclick="startBot()" class="btn btn-success flex-grow-1 fw-bold">START</button>
                    <button onclick="stopBot()" class="btn btn-danger flex-grow-1 fw-bold">STOP</button>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="card p-4 h-100">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span id="statusBadge" class="badge bg-secondary fs-6">Stopped</span>
                    <span class="text-info fw-bold">Data Used: <span id="db">0 B</span></span>
                </div>
                <hr class="mt-0">
                <div id="logBox" class="log-box"></div>
            </div>
        </div>
    </div>
    <script>
        document.getElementById('configForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    sessionid: document.getElementById('sessionid').value,
                    urls: document.getElementById('urls').value.split('\\n').filter(u => u.trim()),
                    comments: document.getElementById('comments').value.split('\\n').filter(c => c.trim()),
                    proxies: document.getElementById('proxies').value.split('\\n').filter(p => p.trim())
                })
            });
            alert('Saved!');
        });
        async function startBot() { await fetch('/api/start', {method: 'POST'}); updateUI(); }
        async function stopBot() { await fetch('/api/stop', {method: 'POST'}); updateUI(); }
        async function updateUI() {
            const res = await fetch('/api/status');
            const data = await res.json();
            const badge = document.getElementById('statusBadge');
            badge.innerText = data.status;
            badge.className = 'badge fs-6 ' + (data.status === 'Running' ? 'bg-success' : 'bg-danger');
            document.getElementById('db').innerText = data.data_formatted;
            document.getElementById('logBox').innerHTML = data.logs.join('<br>');
        }
        setInterval(updateUI, 2000);
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/api/config", methods=["POST"])
def update_config(): bot_state.update(request.json); return jsonify({"success": True})

@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_thread
    if bot_state["status"] == "Running": return jsonify({"error": "Running"})
    stop_event.clear()
    bot_thread = threading.Thread(target=commenting_worker)
    bot_thread.daemon = True
    bot_thread.start()
    return jsonify({"success": True})

@app.route("/api/stop", methods=["POST"])
def stop_bot(): stop_event.set(); return jsonify({"success": True})

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"status": bot_state["status"], "logs": bot_state["logs"], "data_formatted": format_bytes(bot_state["data_bytes_used"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
