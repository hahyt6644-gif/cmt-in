from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import urllib.parse
import threading
import time
import random
import re

app = Flask(__name__)

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
        parts = raw_proxy.split(":")
        if len(parts) == 4:
            return f"socks5://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return raw_proxy
    except: return None

def commenting_worker():
    add_log("Bot starting: Header-Injection Mode")
    bot_state["status"] = "Running"
    
    cl = Client()
    
    # --- ADDED: CUSTOM BROWSER HEADERS ---
    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; V2031 Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.82 Mobile Safari/537.36 Instagram 219.0.0.12.117",
        "Accept-Language": "en-IN,en-US;q=0.9,hi-IN;q=0.8",
        "Sec-CH-UA-Platform": '"Android"',
        "X-IG-App-ID": "936619743392459", # Standard IG App ID
        "X-Requested-With": "com.instagram.android"
    }
    cl.set_user_agent(custom_headers["User-Agent"])
    # --------------------------------------

    cl.is_sync_enabled = False 
    cl.private.hooks['response'].append(data_tracker_hook)
    
    login_successful = False

    while not stop_event.is_set():
        try:
            if bot_state["proxies"]:
                active_proxy = format_proxy(bot_state["proxies"][0])
                if active_proxy:
                    cl.set_proxy(active_proxy)
                    add_log(f"Proxy Bound: {active_proxy.split('@')[-1]}")

            if not login_successful:
                add_log("Authenticating with Browser Headers...")
                # Clean SID
                sid = urllib.parse.unquote(bot_state["sessionid"]).replace(" ", "").replace("\n", "").strip()
                
                cl.login_by_sessionid(sid)
                time.sleep(5) # Pause to let session load
                cl.get_timeline_feed() 
                login_successful = True
                add_log("SUCCESS: Session Validated!")

            for url in bot_state["urls"]:
                if stop_event.is_set(): break
                mid = get_id_offline(url)
                if not mid: continue
                
                try:
                    cl.media_comment(mid, random.choice(bot_state["comments"]))
                    add_log(f"Commented on {mid}")
                except Exception as e:
                    err = str(e).lower()
                    if "checkpoint" in err or "challenge" in err:
                        add_log("SECURITY STOP: Checkpoint required.")
                        bot_state["status"] = "Stopped"; stop_event.set(); return
                    add_log(f"ERR: {err[:40]}")

                # 5-8 Minute Delay
                delay = random.randint(300, 480)
                add_log(f"Safe sleep: {delay // 60}m...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

        except Exception as e:
            err_msg = str(e).lower()
            if "redirect" in err_msg:
                add_log("CRITICAL: Redirect loop. Proxy or Cookie is dead.")
            else:
                add_log(f"FAIL: {err_msg[:50]}")
            bot_state["status"] = "Stopped"; stop_event.set(); break

    bot_state["status"] = "Stopped"

# --- Web UI (Keep the same HTML) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8"><title>SMM Automation (Headers Mode)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.log-box { height: 400px; overflow-y: scroll; background: #000; padding: 15px; font-family: monospace; color: #0f0; border: 1px solid #333; font-size: 13px; }</style>
</head>
<body class="container py-4">
    <div class="row">
        <div class="col-md-5">
            <div class="card p-3 mb-3">
                <input type="password" id="sid" class="form-control mb-2" placeholder="Session ID">
                <textarea id="urls" class="form-control mb-2" rows="5" placeholder="URLs"></textarea>
                <textarea id="msgs" class="form-control mb-2" rows="3" placeholder="Comments"></textarea>
                <textarea id="px" class="form-control mb-2" rows="2" placeholder="Proxy Line"></textarea>
                <button onclick="save()" class="btn btn-primary w-100 mb-2">Save Settings</button>
                <div class="d-flex gap-2">
                    <button onclick="start()" class="btn btn-success w-100 fw-bold">START</button>
                    <button onclick="stop()" class="btn btn-danger w-100 fw-bold">STOP</button>
                </div>
            </div>
        </div>
        <div class="col-md-7">
            <div class="card p-3 mb-3 bg-dark d-flex justify-content-between flex-row">
                <span>Status: <b id="st">Stopped</b></span>
                <span>Data: <b id="db" class="text-info">0 B</b></span>
            </div>
            <div id="logBox" class="log-box"></div>
        </div>
    </div>
    <script>
        async function save() {
            await fetch('/api/config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                sessionid: document.getElementById('sid').value,
                urls: document.getElementById('urls').value.split('\\n').filter(x=>x.trim()),
                comments: document.getElementById('msgs').value.split('\\n').filter(x=>x.trim()),
                proxies: document.getElementById('px').value.split('\\n').filter(x=>x.trim())
            })}); alert("Saved!");
        }
        async function start() { await fetch('/api/start', {method: 'POST'}); }
        async function stop() { await fetch('/api/stop', {method: 'POST'}); }
        setInterval(async () => {
            const r = await fetch('/api/status'); const d = await r.json();
            document.getElementById('st').innerText = d.status;
            document.getElementById('db').innerText = d.data_formatted;
            document.getElementById('logBox').innerHTML = d.logs.join('<br>');
        }, 2000);
    </script>
</body></html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)
@app.route("/api/config", methods=["POST"])
def update_config(): bot_state.update(request.json); return jsonify({"success": True})
@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_thread
    if bot_state["status"] == "Running": return jsonify({"error": "Running"})
    stop_event.clear(); bot_thread = threading.Thread(target=commenting_worker); bot_thread.daemon = True; bot_thread.start()
    return jsonify({"success": True})
@app.route("/api/stop", methods=["POST"])
def stop_bot(): stop_event.set(); return jsonify({"success": True})
@app.route("/api/status", methods=["GET"])
def get_status(): return jsonify({"status": bot_state["status"], "logs": bot_state["logs"], "data_formatted": format_bytes(bot_state["data_bytes_used"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
