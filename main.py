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
        if not url or not isinstance(url, str): return None
        clean_url = url.strip().split("?")[0]
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9\-_]+)", clean_url)
        if match: shortcode = match.group(1)
        elif len(clean_url) <= 15 and not "/" in clean_url: shortcode = clean_url
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
    add_log("Bot starting: Auto-Cleaning Mode")
    bot_state["status"] = "Running"
    
    cl = Client()
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False 
    cl.private.hooks['response'].append(data_tracker_hook)
    cl.public.hooks['response'].append(data_tracker_hook)
    
    login_successful = False

    while not stop_event.is_set():
        try:
            if bot_state["proxies"]:
                p = format_proxy(random.choice(bot_state["proxies"]))
                if p: cl.set_proxy(p)

            if not login_successful:
                add_log("Connecting & Verifying Session...")
                
                # AGGRESSIVE SESSION ID CLEANING
                raw_sid = bot_state["sessionid"]
                clean_sid = urllib.parse.unquote(raw_sid).replace(" ", "").replace("\n", "").replace('"', '').replace("'", "").strip()
                
                cl.login_by_sessionid(clean_sid)
                cl.get_timeline_feed() # Test it
                login_successful = True
                add_log("Session Validated! Login Successful.")

            for item in bot_state["targets"]:
                if stop_event.is_set(): break
                final_ids = []
                
                if item.startswith("@"):
                    user = item.replace("@", "").strip()
                    if user not in post_id_cache:
                        add_log(f"Scanning @{user}...")
                        uid = cl.user_id_from_username(user)
                        medias = cl.user_medias(uid, 3) 
                        post_id_cache[user] = [m.id for m in medias]
                    final_ids = post_id_cache[user]
                else:
                    mid = get_id_offline(item)
                    if mid: final_ids = [mid]

                for mid in final_ids:
                    if stop_event.is_set(): break
                    comment = random.choice(bot_state["comments"])
                    before = bot_state["data_bytes_used"]
                    try:
                        cl.media_comment(mid, comment)
                        used = format_bytes(bot_state["data_bytes_used"] - before)
                        add_log(f"DONE: {mid} | Used: {used}")
                    except Exception as e:
                        err_str = str(e).lower()
                        if "feedback_required" in err_str:
                            add_log("Rate Limit! Sleeping 10 mins...")
                            time.sleep(600)
                        else:
                            add_log(f"ERR: {str(e)[:40]}")
                            # Raise checkpoints to the main try/except block
                            if "checkpoint" in err_str or "challenge" in err_str:
                                raise Exception(e)

                    time.sleep(random.randint(60, 120))

            add_log("Cycle complete. Resting...")
            time.sleep(300)

        except Exception as e:
            err_msg = str(e).lower()
            add_log(f"CRITICAL: {str(e)[:50]}")
            
            # STOP THE BOT IF CHECKPOINT HAPPENS
            if "checkpoint_required" in err_msg or "challenge" in err_msg:
                add_log("STOPPING: IG needs SMS/Email verification! Open your app.")
                bot_state["status"] = "Stopped"
                stop_event.set()
                break
                
            login_successful = False
            time.sleep(60)

    bot_state["status"] = "Stopped"

# --- Web Interface ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMM Ultra-Low Data</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .log-box { height: 400px; overflow-y: scroll; background: #000; padding: 15px; font-family: monospace; color: #0f0; border: 1px solid #333; font-size: 13px; }
        .data-text { font-size: 1.2rem; color: #0dcaf0; font-weight: bold; }
    </style>
</head>
<body class="container py-4">
    <div class="row">
        <div class="col-md-5">
            <div class="card p-3 mb-3">
                <h5 class="text-info">Setup</h5>
                <input type="text" id="sid" class="form-control mb-2" placeholder="Session ID">
                <textarea id="targets" class="form-control mb-2" rows="4" placeholder="URLs or @usernames"></textarea>
                <textarea id="msgs" class="form-control mb-2" rows="3" placeholder="Comments"></textarea>
                <textarea id="px" class="form-control mb-2" rows="3" placeholder="Proxies"></textarea>
                <button onclick="save()" class="btn btn-primary w-100 mb-2">Save Config</button>
                <div class="d-flex gap-2">
                    <button onclick="start()" class="btn btn-success w-100">START</button>
                    <button onclick="stop()" class="btn btn-danger w-100">STOP</button>
                </div>
            </div>
        </div>
        <div class="col-md-7">
            <div class="card p-3 mb-3 bg-dark">
                <div class="d-flex justify-content-between">
                    <span>Status: <b id="st">Stopped</b></span>
                    <span>Session Data: <span id="db" class="data-text">0 B</span></span>
                </div>
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
            alert("Saved");
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
