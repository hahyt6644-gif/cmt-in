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
    if len(bot_state["logs"]) > 50:
        bot_state["logs"].pop()

def format_proxy(raw_proxy):
    """Converts OwlProxy format (host:port:user:pass) to standard (user:pass@host:port)"""
    try:
        raw_proxy = raw_proxy.strip()
        if not raw_proxy: return None
        protocol, rest = raw_proxy.split("://")
        parts = rest.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"{protocol}://{user}:{password}@{host}:{port}"
        return raw_proxy
    except Exception:
        return None

def commenting_worker():
    add_log("Bot thread started.")
    bot_state["status"] = "Running"
    
    cl = Client()
    login_successful = False

    while not stop_event.is_set():
        try:
            # 1. Select a random proxy and apply it
            if bot_state["proxies"]:
                raw_proxy = random.choice(bot_state["proxies"])
                formatted_proxy = format_proxy(raw_proxy)
                if formatted_proxy:
                    cl.set_proxy(formatted_proxy)
                    add_log(f"Using Proxy: {formatted_proxy.split('@')[1]}")

            # 2. Login (Only if not already logged in)
            if not login_successful:
                add_log(f"Attempting login for {bot_state['username']}...")
                cl.login(bot_state["username"], bot_state["password"])
                login_successful = True
                add_log("Login successful!")

            # 3. Process URLs
            for url in bot_state["urls"]:
                if stop_event.is_set():
                    break
                
                comment = random.choice(bot_state["comments"])
                add_log(f"Targeting URL: {url}")
                
                try:
                    # Extract Media ID from URL and post
                    media_id = cl.media_id(cl.media_pk_from_url(url))
                    comment_obj = cl.media_comment(media_id, comment)
                    add_log(f"SUCCESS: Commented '{comment}' on {url}")
                except Exception as e:
                    add_log(f"FAILED on {url} - {str(e)[:50]}")

                # Anti-Ban Delay between comments (30 to 60 seconds)
                delay = random.randint(30, 60)
                add_log(f"Sleeping for {delay} seconds to prevent ban...")
                for _ in range(delay):
                    if stop_event.is_set(): break
                    time.sleep(1)

            add_log("Finished looping through all URLs. Restarting loop...")
            time.sleep(10) # Pause before restarting the loop

        except Exception as e:
            add_log(f"CRITICAL ERROR: {str(e)}")
            add_log("Cooling down for 60 seconds before retrying...")
            login_successful = False # Force re-login
            for _ in range(60):
                if stop_event.is_set(): break
                time.sleep(1)

    bot_state["status"] = "Stopped"
    add_log("Bot thread stopped.")


# --- Web Routes ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMM Auto-Comment Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #121212; color: #ffffff; }
        .card { background-color: #1e1e1e; border: none; }
        .form-control { background-color: #2d2d2d; color: #fff; border: 1px solid #444; }
        .form-control:focus { background-color: #333; color: #fff; }
        .log-box { height: 300px; overflow-y: scroll; background: #000; padding: 10px; font-family: monospace; color: #0f0; border-radius: 5px; }
    </style>
</head>
<body class="container py-4">
    <h2 class="mb-4 text-center text-primary">SMM Comment Automation</h2>
    
    <div class="row">
        <div class="col-md-6 mb-4">
            <div class="card p-4">
                <h4>Configuration</h4>
                <form id="configForm">
                    <div class="row mb-3">
                        <div class="col"><input type="text" id="username" class="form-control" placeholder="IG Username" required></div>
                        <div class="col"><input type="password" id="password" class="form-control" placeholder="IG Password" required></div>
                    </div>
                    <div class="mb-3">
                        <label>Video URLs (One per line)</label>
                        <textarea id="urls" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label>Comments (One per line)</label>
                        <textarea id="comments" class="form-control" rows="3" required></textarea>
                    </div>
                    <div class="mb-3">
                        <label>SOCKS5 Proxies (One per line)</label>
                        <textarea id="proxies" class="form-control" rows="3" placeholder="socks5://change4.owlproxy.com..."></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 mb-2">Save Configuration</button>
                </form>
                
                <div class="d-flex gap-2 mt-3">
                    <button onclick="startBot()" class="btn btn-success flex-grow-1">START BOT</button>
                    <button onclick="stopBot()" class="btn btn-danger flex-grow-1">STOP BOT</button>
                </div>
            </div>
        </div>

        <div class="col-md-6">
            <div class="card p-4">
                <h4>Status: <span id="statusBadge" class="badge bg-secondary">Stopped</span></h4>
                <hr>
                <h5>Live Logs</h5>
                <div id="logBox" class="log-box"></div>
            </div>
        </div>
    </div>

    <script>
        // Handle Form Submission
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
            alert('Configuration Saved!');
        });

        // Start Bot
        async function startBot() {
            await fetch('/api/start', {method: 'POST'});
            updateUI();
        }

        // Stop Bot
        async function stopBot() {
            await fetch('/api/stop', {method: 'POST'});
            updateUI();
        }

        // Update Logs and Status automatically
        async function updateUI() {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            const badge = document.getElementById('statusBadge');
            badge.innerText = data.status;
            badge.className = data.status === 'Running' ? 'badge bg-success' : 'badge bg-danger';

            const logBox = document.getElementById('logBox');
            logBox.innerHTML = data.logs.join('<br>');
        }

        setInterval(updateUI, 2000); // Refresh logs every 2 seconds
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
    # Host 0.0.0.0 makes it accessible on Render or Termux local network
    app.run(host="0.0.0.0", port=5000, debug=True)

