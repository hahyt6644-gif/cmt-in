from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import threading
import time
import random
import re

app = Flask(__name__)

bot_state = {
    "sessionid": "",
    "csrftoken": "",
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
    try:
        req = len(r.request.url) + len(str(r.request.headers)) + len(r.request.body or "")
        res = len(str(r.headers)) + len(r.content)
        bot_state["data_bytes_used"] += (req + res)
    except: pass

def get_id_offline(url):
    try:
        clean_url = url.strip().split("?")[0]
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9\-_]+)", clean_url)
        shortcode = match.group(1) if match else clean_url
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        media_pk = 0
        for char in shortcode: media_pk = (media_pk * 64) + alphabet.index(char)
        return str(media_pk)
    except: return None

def format_proxy(raw_proxy):
    try:
        raw_proxy = raw_proxy.strip().replace("socks5://", "").replace("http://", "")
        if not raw_proxy: return None
        parts = raw_proxy.split(":")
        if len(parts) == 4:
            return f"socks5://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return raw_proxy
    except: return None

def commenting_worker():
    add_log("Bot Started: FORCE-INJECTION MODE 🚀")
    bot_state["status"] = "Running"
    
    cl = Client()
    # Using a safe, generic Indian Android footprint
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False 
    cl.private.hooks['response'].append(data_tracker_hook)

    # 1. BIND PROXY FIRST
    if bot_state["proxies"]:
        active_proxy = format_proxy(bot_state["proxies"][0])
        if active_proxy:
            cl.set_proxy(active_proxy)
            add_log(f"Proxy Connected: {active_proxy.split('@')[-1]}")
            time.sleep(2)

    # 2. FORCE COOKIE INJECTION (Bypassing internal login crashes)
    add_log("Injecting Session & CSRF Directly...")
    sid = bot_state["sessionid"].replace("sessionid=", "").strip()
    csrf = bot_state["csrftoken"].replace("csrftoken=", "").strip()

    cl.public.cookies.set('sessionid', sid, domain='.instagram.com')
    cl.public.cookies.set('csrftoken', csrf, domain='.instagram.com')
    cl.private.cookies.set('sessionid', sid, domain='.instagram.com')
    cl.private.cookies.set('csrftoken', csrf, domain='.instagram.com')
    cl.public.headers.update({"X-CSRFToken": csrf})
    cl.private.headers.update({"X-CSRFToken": csrf})

    add_log("Auth Injected! Starting Operations...")

    # 3. DIRECT COMMENTING LOOP
    while not stop_event.is_set():
        try:
            for url in bot_state["urls"]:
                if stop_event.is_set(): break
                
                mid = get_id_offline(url)
                if not mid: continue
                
                before_data = bot_state["data_bytes_used"]
                comment_text = random.choice(bot_state["comments"])
                
                try:
                    # Posting comment directly via media_comment
                    cl.media_comment(mid, comment_text)
                    used = format_bytes(bot_state["data_bytes_used"] - before_data)
                    add_log(f"✅ DONE: Commented on {url[-15:]} | Data: {used}")
                
                except Exception as e:
                    err = str(e).lower()
                    if "checkpoint" in err or "feedback_required" in err or "challenge" in err:
                        add_log("🚨 ACCOUNT LOCKED: Checkpoint detected.")
                        bot_state["status"] = "Stopped"
                        stop_event.set()
                        return
                    elif "login_required" in err:
                        add_log("❌ SESSION DEAD: Please get new Session ID & CSRF.")
                        bot_state["status"] = "Stopped"
                        stop_event.set()
                        return
                    else:
                        add_log(f"⚠️ FAILED on {url[-10:]}: {err[:40]}")

                # Human-like delay to prevent spam blocks (3 to 6 mins)
                delay = random.randint(180, 360)
                add_log(f"Sleeping for {delay // 60}m {delay % 60}s to prevent ban...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            if not stop_event.is_set():
                add_log("All URLs processed. Waiting 10m before looping...")
                time.sleep(600)

        except Exception as e:
            add_log(f"System Error: {str(e)[:50]}")
            time.sleep(60)

    bot_state["status"] = "Stopped"


# --- WEB DASHBOARD UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMM Automation Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; background-color: #0d1117; color: #c9d1d9; }
        .card { background-color: #161b22; border: 1px solid #30363d; }
        .log-box { height: 380px; overflow-y: scroll; background: #010409; padding: 15px; font-family: monospace; color: #3fb950; border-radius: 8px; border: 1px solid #30363d; font-size: 13px; }
    </style>
</head>
<body class="container">
    <h3 class="mb-4 text-center text-primary fw-bold">🚀 SMM Bot (Force-Injection Mode)</h3>
    <div class="row">
        <div class="col-lg-5 mb-4">
            <div class="card p-4">
                <input type="password" id="sid" class="form-control mb-3 bg-dark text-light" placeholder="Session ID (Paste here)" required>
                <input type="password" id="csrf" class="form-control mb-3 bg-dark text-light" placeholder="CSRF Token (Paste here)" required>
                <textarea id="urls" class="form-control mb-3 bg-dark text-light" rows="4" placeholder="Paste Video URLs here..." required></textarea>
                <textarea id="msgs" class="form-control mb-3 bg-dark text-light" rows="2" placeholder="Paste Comments here..." required></textarea>
                <textarea id="px" class="form-control mb-3 bg-dark text-light" rows="2" placeholder="SOCKS5 Proxy (Host:Port:User:Pass)"></textarea>
                
                <button onclick="save()" class="btn btn-outline-primary w-100 mb-3 fw-bold">💾 Save Configuration</button>
                <div class="d-flex gap-2">
                    <button onclick="start()" class="btn btn-success flex-grow-1 fw-bold">▶️ START</button>
                    <button onclick="stop()" class="btn btn-danger flex-grow-1 fw-bold">⏹️ STOP</button>
                </div>
            </div>
        </div>
        <div class="col-lg-7">
            <div class="card p-4 h-100">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <span class="fs-5">Status: <span id="st" class="badge bg-secondary">Stopped</span></span>
                    <span class="text-info fw-bold">Data Used: <span id="db">0 B</span></span>
                </div>
                <div id="logBox" class="log-box">Waiting to start...</div>
            </div>
        </div>
    </div>
    <script>
        async function save() {
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    sessionid: document.getElementById('sid').value,
                    csrftoken: document.getElementById('csrf').value,
                    urls: document.getElementById('urls').value.split('\\n').filter(x=>x.trim()),
                    comments: document.getElementById('msgs').value.split('\\n').filter(x=>x.trim()),
                    proxies: document.getElementById('px').value.split('\\n').filter(x=>x.trim())
                })
            }); 
            alert("Settings Saved! Ready to Start.");
        }
        async function start() { await fetch('/api/start', {method: 'POST'}); }
        async function stop() { await fetch('/api/stop', {method: 'POST'}); }
        setInterval(async () => {
            const r = await fetch('/api/status'); 
            const d = await r.json();
            const badge = document.getElementById('st');
            badge.innerText = d.status;
            badge.className = 'badge ' + (d.status === 'Running' ? 'bg-success' : 'bg-danger');
            document.getElementById('db').innerText = d.data_formatted;
            document.getElementById('logBox').innerHTML = d.logs.join('<br>');
        }, 2000);
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
def get_status(): return jsonify({"status": bot_state["status"], "logs": bot_state["logs"], "data_formatted": format_bytes(bot_state["data_bytes_used"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
