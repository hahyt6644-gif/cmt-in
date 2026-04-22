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
    add_log("Bot starting: Instagrapi + CSRF Fix Mode")
    bot_state["status"] = "Running"
    
    cl = Client()
    cl.set_user_agent("Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2280; vivo; V2031; v2031; qcom; en_IN; 332155050)")
    cl.is_sync_enabled = False 
    cl.private.hooks['response'].append(data_tracker_hook)

    try:
        # 1. Set Proxy First
        if bot_state["proxies"]:
            active_proxy = format_proxy(bot_state["proxies"][0])
            if active_proxy:
                cl.set_proxy(active_proxy)
                add_log(f"Proxy Locked: {active_proxy.split('@')[-1]}")
                time.sleep(3)

        # 2. Inject Session & CSRF Directly
        add_log("Injecting Auth Tokens into Instagrapi...")
        sid = urllib.parse.unquote(bot_state["sessionid"]).replace(" ", "").strip()
        csrf = bot_state["csrftoken"].replace(" ", "").strip()

        # The Fix: Manually feed CSRF to prevent "missing" error
        cl.public.cookies.set('csrftoken', csrf, domain='.instagram.com')
        cl.private.cookies.set('csrftoken', csrf, domain='.instagram.com')
        cl.public.headers.update({"X-CSRFToken": csrf})
        cl.private.headers.update({"X-CSRFToken": csrf})

        cl.login_by_sessionid(sid)
        time.sleep(3)
        cl.get_timeline_feed()
        add_log("✅ SUCCESS: Login Verified in Instagrapi!")

    except Exception as e:
        err = str(e).lower()
        if "checkpoint" in err or "challenge" in err:
            add_log("🚨 CHECKPOINT: Account needs verification.")
        else:
            add_log(f"❌ LOGIN FAILED: {err[:50]}")
        bot_state["status"] = "Stopped"
        stop_event.set()
        return

    # 3. Commenting Loop
    while not stop_event.is_set():
        try:
            for url in bot_state["urls"]:
                if stop_event.is_set(): break
                
                mid = get_id_offline(url)
                if not mid: continue
                
                before_data = bot_state["data_bytes_used"]
                try:
                    cl.media_comment(mid, random.choice(bot_state["comments"]))
                    used = format_bytes(bot_state["data_bytes_used"] - before_data)
                    add_log(f"✅ DONE: Commented on {url[-15:]} | Data: {used}")
                except Exception as e:
                    err = str(e).lower()
                    if "checkpoint" in err or "feedback_required" in err:
                        add_log("SECURITY STOP: Checkpoint detected.")
                        bot_state["status"] = "Stopped"; stop_event.set(); return
                    add_log(f"Comment Failed: {err[:40]}")

                # Human Delay: 3 to 6 minutes
                delay = random.randint(180, 360)
                add_log(f"Resting for {delay // 60}m {delay % 60}s...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            if not stop_event.is_set():
                add_log("List complete. Waiting 10m before restarting...")
                time.sleep(600)

        except Exception as e:
            add_log(f"System Error: {str(e)[:50]}")
            time.sleep(60)

    bot_state["status"] = "Stopped"

# --- Web UI ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8"><title>SMM Automation (Instagrapi Mode)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.log-box { height: 350px; overflow-y: scroll; background: #0d1117; padding: 15px; font-family: monospace; color: #0f0; border-radius: 8px; border: 1px solid #30363d; font-size: 13px; }</style>
</head>
<body class="container py-4">
    <h3 class="mb-3 text-info fw-bold text-center">SMM Automation (Instagrapi Mode)</h3>
    <div class="row">
        <div class="col-md-5">
            <div class="card p-3 mb-3">
                <input type="password" id="sid" class="form-control mb-2" placeholder="Session ID (e.g. 2719...)">
                <input type="password" id="csrf" class="form-control mb-2" placeholder="CSRF Token (e.g. UmQlLr...)">
                <textarea id="urls" class="form-control mb-2" rows="4" placeholder="Video URLs"></textarea>
                <textarea id="msgs" class="form-control mb-2" rows="2" placeholder="Comments"></textarea>
                <textarea id="px" class="form-control mb-2" rows="2" placeholder="SOCKS5 Proxy (1st Line Used)"></textarea>
                <button onclick="save()" class="btn btn-primary w-100 mb-2 fw-bold">Save Settings</button>
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
                csrftoken: document.getElementById('csrf').value,
                urls: document.getElementById('urls').value.split('\\n').filter(x=>x.trim()),
                comments: document.getElementById('msgs').value.split('\\n').filter(x=>x.trim()),
                proxies: document.getElementById('px').value.split('\\n').filter(x=>x.trim())
            })}); alert("Saved Successfully!");
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
