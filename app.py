from flask import Flask, request, render_template_string
import requests, sqlite3, qrcode, base64, random, string
from io import BytesIO
from datetime import datetime

app = Flask(__name__)
API_KEY = "fbff309716966604f45e6fb7891dbfdcd849d"
DB = "links.db"

def init_db():
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS links(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        long_url TEXT, short_url TEXT, alias TEXT, note TEXT, created_at TEXT)""")
    con.commit(); con.close()

def save(long_url, short_url, alias, note):
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("INSERT INTO links VALUES(NULL,?,?,?,?,?)",
                (long_url, short_url, alias, note, datetime.utcnow().isoformat()))
    con.commit(); con.close()

def qr(text):
    q = qrcode.QRCode(box_size=3, border=2); q.add_data(text); q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def random_slug(n=3):
    return "".join(random.choice(string.ascii_lowercase+string.digits) for _ in range(n))

def cuttly(long_url, alias):
    p = {"key": API_KEY, "short": long_url}
    if alias: p["name"] = alias
    r = requests.get("https://cutt.ly/api/api.php", params=p).json()["url"]
    s = r["status"]
    if s == 3 and alias:
        alias2 = alias + "-" + random_slug()
        r2 = requests.get("https://cutt.ly/api/api.php",
               params={"key": API_KEY, "short": long_url, "name": alias2}).json()["url"]
        return (r2["shortLink"], f"Used {alias2}") if r2["status"] in (1,7) else (None, "Slug fail")
    if s in (1,7): return r["shortLink"], ""
    return None, f"Error {s}"

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mini URL Shortener</title>
  <!-- Bootstrap 5 CDN -->
  <link
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
    rel="stylesheet">
</head>
<body class="bg-dark text-light">
  <div class="container py-5">
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card shadow-lg">
          <div class="card-body">
            <h3 class="card-title mb-3 text-center">Mini URL Shortener</h3>

            {% if error %}
              <div class="alert alert-danger">{{ error }}</div>
            {% endif %}
            {% if note %}
              <div class="alert alert-warning">{{ note }}</div>
            {% endif %}

            <form method="post" class="mb-3">
              <div class="mb-3">
                <label class="form-label">Long URL</label>
                <input name="long_url" class="form-control"
                       placeholder="https://example.com">
              </div>
              <div class="mb-3">
                <label class="form-label">Slug (optional)</label>
                <input name="alias" class="form-control"
                       placeholder="my-short-link">
              </div>
              <button class="btn btn-primary w-100">Shorten</button>
            </form>

            {% if short_url %}
              <hr>
              <p class="mb-1"><strong>Short URL</strong></p>
              <p>
                <a href="{{ short_url }}" target="_blank">
                  {{ short_url }}
                </a>
              </p>
              <img src="{{ qr }}" alt="QR code"
                   class="img-thumbnail d-block mx-auto">
            {% endif %}
          </div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

@app.route("/", methods=["GET","POST"])
def index():
    short_url = qr_img = error = note = ""
    if request.method == "POST":
        url = request.form.get("long_url","").strip()
        alias = request.form.get("alias","").strip() or None
        if not url: error="Enter a URL."
        else:
            short_url, note = cuttly(url, alias)
            if short_url:
                qr_img = qr(short_url); save(url, short_url, alias, note)
            else: error = note
    return render_template_string(HTML, short_url=short_url, qr=qr_img, error=error, note=note)

if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=True)
