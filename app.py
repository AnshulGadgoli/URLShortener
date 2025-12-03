from flask import Flask, request, render_template_string, url_for
import requests, sqlite3, qrcode, base64, random, string
from io import BytesIO
from datetime import datetime

app = Flask(__name__)

# Put your Cutt.ly API key here (inside quotes)
CUTTLY_API_KEY = "fbff309716966604f45e6fb7891dbfdcd849d"
DB_PATH = "links.db"


# ---------- DB HELPERS ----------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            long_url TEXT NOT NULL,
            short_url TEXT NOT NULL,
            alias TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_link(long_url, short_url, alias, note):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO links (long_url, short_url, alias, note, created_at) VALUES (?,?,?,?,?)",
        (long_url, short_url, alias, note, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_recent_links(limit=30):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, long_url, short_url, alias, note, created_at "
        "FROM links ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


# ---------- QR HELPER ----------

def qr_data_uri(text: str) -> str:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return "data:image/png;base64," + b64


# ---------- CUTT.LY SHORTENER ----------

def random_suffix(n=3) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def call_cuttly(long_url: str, alias: str | None):
    key = (CUTTLY_API_KEY or "").strip()
    if not key:
        return None, "Set your Cutt.ly API key in CUTTLY_API_KEY."

    params = {"key": key, "short": long_url}
    if alias:
        params["name"] = alias

    try:
        resp = requests.get("https://cutt.ly/api/api.php", params=params, timeout=10)
    except Exception as e:
        return None, f"Network error talking to Cutt.ly: {e}"

    try:
        data = resp.json()
    except Exception:
        return None, f"Cutt.ly returned non-JSON: {resp.text[:200]}"

    if not isinstance(data, dict):
        return None, f"Unexpected JSON from Cutt.ly: {str(data)[:200]}"

    url_info = data.get("url")
    if not isinstance(url_info, dict):
        return None, f"Unexpected 'url' field from Cutt.ly: {str(url_info)[:200]}"

    return url_info, None


def shorten_with_cuttly(long_url: str, alias: str | None):
    """
    Returns: (short_url, notice_message, error_message)
    """
    # First attempt with given alias (or None)
    info, err = call_cuttly(long_url, alias)
    if err:
        return None, None, err
    status = info.get("status")

    # 1,7 OK; 2 bad URL; 3 alias taken; 4 bad key; 5 invalid chars; 6 blocked; 8 limit
    if status == 3 and alias:
        new_alias = f"{alias}-{random_suffix()}"
        info2, err2 = call_cuttly(long_url, new_alias)
        if err2:
            return None, None, err2
        status2 = info2.get("status")
        if status2 in (1, 7):
            return info2.get("shortLink"), f"Slug '{alias}' was taken, used '{new_alias}'.", None
        return None, None, "Slug was taken and fallback also failed."

    if status in (1, 7):
        return info.get("shortLink"), None, None
    if status == 2:
        return None, None, "That does not look like a valid URL."
    if status == 4:
        return None, None, "Cutt.ly says your API key is invalid."
    if status == 5:
        return None, None, "URL did not pass Cutt.ly validation."
    if status == 6:
        return None, None, "Domain is blocked by Cutt.ly."
    if status == 8:
        return None, None, "You hit your monthly Cutt.ly limit."

    return None, None, f"Cutt.ly returned status code {status}."


# ---------- HTML TEMPLATES ----------

HTML_MAIN = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mini URL Shortener</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#020617;background:linear-gradient(135deg,#111827,#020617);color:#f9fafb}
a{color:#a5b4fc;text-decoration:none}a:hover{text-decoration:underline}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{width:100%;max-width:640px;background:#020617;border-radius:18px;padding:22px 26px 26px;
      box-shadow:0 18px 40px rgba(0,0,0,.6);border:1px solid rgba(148,163,184,.4)}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.title{font-size:1.5rem}.sub{font-size:.9rem;color:#9ca3af}
.badge{padding:3px 8px;border-radius:999px;font-size:.75rem;background:rgba(148,163,184,.25)}
.nav{margin-top:4px;font-size:.8rem}.nav a{margin-right:10px}
label{font-size:.85rem;display:block;margin-bottom:4px}
input[type=text]{width:100%;padding:9px 11px;border-radius:10px;border:1px solid #4b5563;
                background:#020617;color:#e5e7eb;font-size:.9rem}
input[type=text]:focus{border-color:#6366f1;outline:none;box-shadow:0 0 0 1px rgba(99,102,241,.4)}
.hint{font-size:.75rem;color:#9ca3af;margin-top:3px}
.btn{margin-top:10px;padding:8px 16px;border-radius:999px;border:none;
     background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:.9rem;cursor:pointer}
.btn:hover{opacity:.9}
.error,.notice,.result{margin-top:12px;padding:9px 11px;border-radius:10px;font-size:.9rem}
.error{background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.6)}
.notice{background:rgba(234,179,8,.1);border:1px solid rgba(234,179,8,.5)}
.result{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.5)}
.qr{margin-top:8px;display:inline-flex;flex-direction:column;align-items:center;gap:4px}
.qr img{background:#fff;border-radius:8px;padding:6px}
</style>
</head>
<body>
<div class="wrap"><div class="card">
<div class="top">
 <div>
  <div class="title">Mini URL Shortener</div>
  <div class="sub">Custom slugs, QR & history with Cutt.ly</div>
  <div class="nav"><a href="{{ url_for('index') }}">Shorten</a>·<a href="{{ url_for('history') }}">History</a></div>
 </div>
 <div class="badge">Python · Flask</div>
</div>

{% if error %}<div class="error">{{ error }}</div>{% endif %}
{% if notice %}<div class="notice">{{ notice }}</div>{% endif %}

<form method="post">
 <label>Long URL</label>
 <input type="text" name="long_url" placeholder="https://www.youtube.com/watch?v=..." required>
 <div style="height:8px"></div>
 <label>Custom slug (optional)</label>
 <input type="text" name="alias" placeholder="yt123 → cutt.ly/yt123">
 <div class="hint">Leave empty for random code. If slug is taken, a random suffix is added.</div>
 <button class="btn" type="submit">Shorten URL</button>
</form>

{% if short_url %}
<div class="result">
 <strong>Short URL:</strong><br>
 <a href="{{ short_url }}" target="_blank">{{ short_url }}</a>
 {% if short_qr %}
 <div class="qr">
  <img src="{{ short_qr }}" alt="QR">
  <div class="hint">Scan to open</div>
 </div>
 {% endif %}
</div>
{% endif %}

</div></div>
</body>
</html>
"""

HTML_HISTORY = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Short Link History</title>
<style>
body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#020617;color:#e5e7eb}
a{color:#a5b4fc;text-decoration:none}a:hover{text-decoration:underline}
.wrap{min-height:100vh;padding:24px}
.card{max-width:900px;margin:0 auto}
.title{font-size:1.5rem;margin-bottom:4px}
.sub{font-size:.9rem;color:#9ca3af;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:7px 6px;border-bottom:1px solid #111827;vertical-align:top}
th{text-align:left;color:#9ca3af;font-weight:500}
tr:nth-child(even){background:#020617}tr:nth-child(odd){background:#030712}
.small{font-size:.75rem;color:#9ca3af}
</style>
</head>
<body>
<div class="wrap"><div class="card">
<div class="title">Short Link History</div>
<div class="sub">Last {{ links|length }} links · <a href="{{ url_for('index') }}">Back</a></div>
{% if links %}
<table>
 <tr><th>ID</th><th>Short URL</th><th>Long URL</th><th>Slug / note</th><th>Created (UTC)</th></tr>
 {% for r in links %}
 <tr>
  <td>{{ r.id }}</td>
  <td><a href="{{ r.short_url }}" target="_blank">{{ r.short_url }}</a></td>
  <td><span class="small">{{ r.long_url }}</span></td>
  <td>
   {% if r.alias %}<div>Slug: <code>{{ r.alias }}</code></div>{% endif %}
   {% if r.note %}<div class="small">{{ r.note }}</div>{% endif %}
  </td>
  <td><span class="small">{{ r.created_at }}</span></td>
 </tr>
 {% endfor %}
</table>
{% else %}
<p>No links yet. <a href="{{ url_for('index') }}">Create one</a>.</p>
{% endif %}
</div></div>
</body>
</html>
"""


# ---------- ROUTES ----------

@app.before_request
def setup():
    init_db()

@app.route("/", methods=["GET", "POST"])
def index():
    short_url = short_qr = notice = error = None

    if request.method == "POST":
        long_url = (request.form.get("long_url") or "").strip()
        alias = (request.form.get("alias") or "").strip() or None

        if not long_url:
            error = "Please enter a URL."
        else:
            short_url, notice, err = shorten_with_cuttly(long_url, alias)
            if err:
                error = err
                short_url = None
                notice = None
            else:
                save_link(long_url, short_url, alias, notice)
                short_qr = qr_data_uri(short_url)

    # On GET: everything is None → clean page with just the form
    return render_template_string(
        HTML_MAIN,
        short_url=short_url,
        short_qr=short_qr,
        notice=notice,
        error=error,
    )


@app.route("/history")
def history():
    rows = get_recent_links()
    class Row: pass
    objs = []
    for row in rows:
        r = Row()
        r.id, r.long_url, r.short_url, r.alias, r.note, r.created_at = row
        objs.append(r)
    return render_template_string(HTML_HISTORY, links=objs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
