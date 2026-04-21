from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import urllib.parse
import threading
import time
import random
import re

app = Flask(__name__)

bot_state = {
    "sessionid": "",
    "targets": [],
    "comments": [],
    "proxies": [],
    "status": "Stopped",
    "logs": [],
    "data_bytes_used": 0
}

post_id_cache = {} 
stop_event = threading.Event()

def add_log(message):
    bot_state["logs"].insert(0, f"{time.strftime('%H:%M:%S')} - {message}")
    if len(bot_state["logs"]) > 50: bot_state["logs"].pop()

def format_bytes(size):
    if size < 1024: return f"{size} B"
    return f"{size / 1024:.2f} KB"

def data_tracker_hook(r, *args, **kwargs):
    try:
        req = len(r.request.url) + len(str(r.request.headers)) + len(r.request.body or "")
        res = len(str(r.headers)) + len(r.content)
        bot_state["data_bytes_used"] += (req + res)
    except: pass

def get_id_offline(url):
    """Math conversion - 0 KB Data used"""
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
        clean_px = raw_proxy.strip().replace("socks5://", "").replace("http://", "")
        parts = clean_px.split(":")
        if len(parts) == 4:
            return f"socks5://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return raw_proxy
    except: return None

def commenting_worker():
    add_log("Bot starting: 5-7 Min Delay Mode")
    bot_state["status"] = "Running"
    
    cl = Client()
    # Matching Indian Mobile User-Agent
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False 
    cl.private.hooks['response'].append(data_tracker_hook)
    cl.public.hooks['response'].append(data_tracker_hook)
    
    login_successful = False

    while not stop_event.is_set():
        try:
            if bot_state["proxies"]:
                cl.set_proxy(format_proxy(random.choice(bot_state["proxies"])))

            if not login_successful:
                add_log("Connecting Session...")
                # Auto-clean Session ID to prevent 'Invalid sessionid'
                sid = urllib.parse.unquote(bot_state["sessionid"]).replace(" ", "").replace("\n", "").strip()
                cl.login_by_sessionid(sid)
                cl.get_timeline_feed() 
                login_successful = True
                add_log("SUCCESS: Session Validated!")

            for item in bot_state["targets"]:
                if stop_event.is_set(): break
                
                mid = get_id_offline(item)
                if not mid: continue

                comment = random.choice(bot_state["comments"])
                before = bot_state["data_bytes_used"]
                
                try:
                    cl.media_comment(mid, comment)
                    used = format_bytes(bot_state["data_bytes_used"] - before)
                    add_log(f"COMMENTED: {mid} | Data: {used}")
                except Exception as e:
                    if "checkpoint" in str(e).lower():
                        add_log("STOPPED: Checkpoint Required. Open IG app.")
                        bot_state["status"] = "Stopped"
                        stop_event.set()
                        return
                    add_log(f"ERR: {str(e)[:40]}")

                # 5-7 MINUTE DELAY (300 to 420 seconds)
                delay = random.randint(300, 420)
                add_log(f"Waiting {delay // 60}m {delay % 60}s...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            add_log("List finished. Resting 10m...")
            time.sleep(600)

        except Exception as e:
            add_log(f"CRITICAL: {str(e)[:50]}")
            login_successful = False
            time.sleep(60)

    bot_state["status"] = "Stopped"

# --- Web Interface ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <title>SMM Ultra-Low Data (5-7m Delay)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .log-box { height: 450px; overflow-y: scroll; background: #000; padding: 15px; font-family: monospace; color: #0f0; border: 1px solid #333; font-size: 13px; }
        .data-text { font-size: 1.2rem; color: #0dcaf0; font-weight: bold; }
    </style>
</head>
<body class="container py-4">
    <div class="row">
        <div class="col-md-5">
            <div class="card p-3 mb-3">
                <h6 class="text-info">Configuration</h6>
                <input type="text" id="sid" class="form-control mb-2" placeholder="Paste Session ID">
                <textarea id="targets" class="form-control mb-2" rows="5" placeholder="URLs (one per line)"></textarea>
                <textarea id="msgs" class="form-control mb-2" rows="3" placeholder="Comments"></textarea>
                <textarea id="px" class="form-control mb-2" rows="3" placeholder="Proxies"></textarea>
                <button onclick="save()" class="btn btn-primary w-100 mb-2">Save Settings</button>
                <div class="d-flex gap-2">
                    <button onclick="start()" class="btn btn-success w-100 fw-bold">START BOT</button>
                    <button onclick="stop()" class="btn btn-danger w-100 fw-bold">STOP</button>
                </div>
            </div>
        </div>
        <div class="col-md-7">
            <div class="card p-3 mb-3 bg-dark d-flex justify-content-between flex-row">
                <span>Status: <b id="st">Stopped</b></span>
                <span>Data Used: <span id="db" class="data-text">0 B</span></span>
            </div>
            <div id="logs" class="log-box"></div>
        </div>
    </div>
    <script>
        async function save() {
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    sessionid: document.getElementById('sid').value,
                    targets: document.getElementById('targets').value.split('\\n').filter(x=>x.trim()),
                    comments: document.getElementById('msgs').value.split('\\n').filter(x=>x.trim()),
                    proxies: document.getElementById('px').value.split('\\n').filter(x=>x.trim())
                })
            });
            alert("Configuration Saved!");
        }
        async function start() { await fetch('/api/start', {method:'POST'}); }
        async function stop() { await fetch('/api/stop', {method:'POST'}); }
        setInterval(async () => {
            const r = await fetch('/api/status');
            const d = await r.json();
            document.getElementById('st').innerText = d.status;
            document.getElementById('db').innerText = d.data_formatted;
            document.getElementById('logs').innerHTML = d.logs.join('<br>');
        }, 2000);
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/api/config", methods=["POST"])
def update_config():
    bot_state.update(request.json)
    return jsonify({"success": True})

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
def stop_bot():
    stop_event.set()
    return jsonify({"success": True})

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "status": bot_state["status"],
        "logs": bot_state["logs"],
        "data_formatted": format_bytes(bot_state["data_bytes_used"])
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    
