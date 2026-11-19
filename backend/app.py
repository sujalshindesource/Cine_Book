"""CineBook backend - Flask + SQLite.
Data structures used: 2D matrix (seat layout), HashMaps (booking/user index),
FIFO queue/deque (waitlist per show), sorted order (shows by time),
max-heap via heapq (top movies), per-show Lock (no double booking)."""
import os, sqlite3, threading, heapq
from collections import deque, defaultdict
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cinema.db")
MAX_SEATS = 6
app = Flask(__name__)
ser = URLSafeTimedSerializer(os.environ.get("SECRET_KEY", "cinebook-dev-secret"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER');
CREATE TABLE IF NOT EXISTS movies(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, genre TEXT,
  duration INTEGER, rating REAL, description TEXT);
CREATE TABLE IF NOT EXISTS shows(id INTEGER PRIMARY KEY AUTOINCREMENT, movie_id INTEGER NOT NULL,
  screen TEXT NOT NULL, show_time TEXT NOT NULL, price REAL NOT NULL, n_rows INTEGER NOT NULL, n_cols INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS seats(id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL,
  seat_row INTEGER NOT NULL, seat_col INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'AVAILABLE', booking_id INTEGER,
  UNIQUE(show_id, seat_row, seat_col));
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, show_id INTEGER NOT NULL,
  total REAL NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT, cancelled_at TEXT);
CREATE TABLE IF NOT EXISTS booking_seats(booking_id INTEGER NOT NULL, seat_id INTEGER NOT NULL, PRIMARY KEY(booking_id, seat_id));
CREATE TABLE IF NOT EXISTS waitlist(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, show_id INTEGER NOT NULL,
  seats_wanted INTEGER NOT NULL, joined_at TEXT, status TEXT NOT NULL DEFAULT 'WAITING');
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, message TEXT NOT NULL,
  created_at TEXT, is_read INTEGER NOT NULL DEFAULT 0);
"""

# ---------------------------------------------------------------- DB helpers
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def now_show(): return datetime.now().strftime("%Y-%m-%dT%H:%M")
def err(msg, code=400): return jsonify({"error": msg}), code
def label(r, c): return f"{chr(65 + r)}{c + 1}"

SHOW_SQL = """SELECT sh.*, m.title, m.genre,
 (SELECT COUNT(*) FROM seats WHERE show_id=sh.id AND status='AVAILABLE') AS free,
 (SELECT COUNT(*) FROM seats WHERE show_id=sh.id AND status='BOOKED') AS booked,
 (SELECT COUNT(*) FROM seats WHERE show_id=sh.id AND status='BLOCKED') AS blocked,
 (SELECT COUNT(*) FROM waitlist WHERE show_id=sh.id AND status='WAITING') AS waiting
 FROM shows sh JOIN movies m ON m.id=sh.movie_id """

# ------------------------------------------------------- data structures
class SeatMatrix:
    """2D array of (status, booking_id) for one show -> O(1) seat check/update."""
    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.grid = [[("AVAILABLE", None)] * cols for _ in range(rows)]
    def is_free(self, r, c): return self.grid[r][c][0] == "AVAILABLE"
    def free_count(self): return sum(self.is_free(r, c) for r in range(self.rows) for c in range(self.cols))
    def find_contiguous(self, n):
        """Scan rows (middle rows first) for n adjacent free seats."""
        for r in sorted(range(self.rows), key=lambda x: abs(x - self.rows // 2)):
            run = []
            for c in range(self.cols):
                run = run + [(r, c)] if self.is_free(r, c) else []
                if len(run) == n: return run
        return None
    def pick(self, n):
        free = [(r, c) for r in range(self.rows) for c in range(self.cols) if self.is_free(r, c)]
        return self.find_contiguous(n) or free[:n]

def load_matrix(show_id):
    sh = q("SELECT n_rows, n_cols FROM shows WHERE id=?", (show_id,), one=True)
    m = SeatMatrix(sh["n_rows"], sh["n_cols"])
    for s in q("SELECT seat_row, seat_col, status, booking_id FROM seats WHERE show_id=?", (show_id,)):
        m.grid[s["seat_row"]][s["seat_col"]] = (s["status"], s["booking_id"])
    return m

BOOKING_INDEX = {}                 # HashMap: bookingId -> {user_id, show_id, status}
USER_INDEX = defaultdict(list)     # HashMap: userId -> [bookingIds]
WAITLIST_Q = defaultdict(deque)    # FIFO queue per show: waitlist ids
SHOW_LOCKS = defaultdict(threading.Lock)  # one lock per show

def index_add(bid, uid, sid, status="ACTIVE"):
    BOOKING_INDEX[bid] = {"user_id": uid, "show_id": sid, "status": status}
    if bid not in USER_INDEX[uid]: USER_INDEX[uid].append(bid)

def rebuild_indexes():
    BOOKING_INDEX.clear(); USER_INDEX.clear(); WAITLIST_Q.clear()
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row
    for b in c.execute("SELECT id,user_id,show_id,status FROM bookings ORDER BY id"):
        index_add(b["id"], b["user_id"], b["show_id"], b["status"])
    for w in c.execute("SELECT id,show_id FROM waitlist WHERE status='WAITING' ORDER BY joined_at, id"):
        WAITLIST_Q[w["show_id"]].append(w["id"])
    c.close()

# ------------------------------------------------------------ core logic
class SeatTaken(Exception): pass

def notify(uid, msg):
    db().execute("INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)", (uid, msg, now()))

def create_booking(uid, show, picks, source="DIRECT"):
    """Atomic: each seat is claimed with UPDATE ... WHERE status='AVAILABLE'. Caller holds show lock."""
    d = db()
    bid = d.execute("INSERT INTO bookings(user_id,show_id,total,status,source,created_at) VALUES(?,?,?,?,?,?)",
                    (uid, show["id"], show["price"] * len(picks), "ACTIVE", source, now())).lastrowid
    for r, c in picks:
        u = d.execute("UPDATE seats SET status='BOOKED', booking_id=? WHERE show_id=? AND seat_row=? AND seat_col=? AND status='AVAILABLE'",
                      (bid, show["id"], r, c))
        if u.rowcount != 1:
            d.rollback(); raise SeatTaken()
        sid = d.execute("SELECT id FROM seats WHERE show_id=? AND seat_row=? AND seat_col=?", (show["id"], r, c)).fetchone()[0]
        d.execute("INSERT INTO booking_seats VALUES(?,?)", (bid, sid))
    d.commit()
    index_add(bid, uid, show["id"])
    return bid

def process_waitlist(show_id):
    """After seats are freed: walk the FIFO queue from the front; allot to every request that now fits."""
    show = q(SHOW_SQL + "WHERE sh.id=?", (show_id,), one=True)
    if not show: return
    queue, remaining = WAITLIST_Q[show_id], deque()
    while queue:
        wid = queue.popleft()
        w = q("SELECT * FROM waitlist WHERE id=? AND status='WAITING'", (wid,), one=True)
        if not w: continue
        m = load_matrix(show_id)
        if m.free_count() >= w["seats_wanted"]:
            picks = m.pick(w["seats_wanted"])
            bid = create_booking(w["user_id"], show, picks, "WAITLIST")
            db().execute("UPDATE waitlist SET status='FULFILLED' WHERE id=?", (wid,))
            notify(w["user_id"], f"Good news! {len(picks)} seat(s) ({', '.join(label(r, c) for r, c in picks)}) for "
                                 f"{show['title']} were allotted from the waitlist. Booking #{bid}.")
            db().commit()
        else:
            remaining.append(wid)
    WAITLIST_Q[show_id] = remaining

def get_booking(bid): return q("SELECT * FROM bookings WHERE id=?", (bid,), one=True)

def booking_view(b):
    seats = q("SELECT s.seat_row r, s.seat_col c FROM booking_seats bs JOIN seats s ON s.id=bs.seat_id WHERE bs.booking_id=? ORDER BY r,c", (b["id"],))
    sh = q("SELECT sh.screen, sh.show_time, sh.id show_id, m.title FROM shows sh JOIN movies m ON m.id=sh.movie_id WHERE sh.id=?", (b["show_id"],), one=True)
    u = q("SELECT name,email FROM users WHERE id=?", (b["user_id"],), one=True)
    return {"id": b["id"], "status": b["status"], "source": b["source"], "total": b["total"], "created_at": b["created_at"],
            "cancelled_at": b["cancelled_at"], "seats": [label(s["r"], s["c"]) for s in seats], "title": sh["title"],
            "screen": sh["screen"], "show_time": sh["show_time"], "show_id": sh["show_id"],
            "user_name": u["name"], "user_email": u["email"]}

def delete_show(sid):
    d = db()
    d.execute("DELETE FROM booking_seats WHERE booking_id IN (SELECT id FROM bookings WHERE show_id=?)", (sid,))
    for t in ("bookings", "waitlist", "seats"): d.execute(f"DELETE FROM {t} WHERE show_id=?", (sid,))
    d.execute("DELETE FROM shows WHERE id=?", (sid,)); d.commit(); rebuild_indexes()

def make_show(movie_id, screen, show_time, price, n_rows, n_cols):
    d = db()
    sid = d.execute("INSERT INTO shows(movie_id,screen,show_time,price,n_rows,n_cols) VALUES(?,?,?,?,?,?)",
                    (movie_id, screen, show_time, price, n_rows, n_cols)).lastrowid
    d.executemany("INSERT INTO seats(show_id,seat_row,seat_col) VALUES(?,?,?)",
                  [(sid, r, c) for r in range(n_rows) for c in range(n_cols)])
    d.commit(); return sid

# ------------------------------------------------------------------ auth
def current_user():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "): return None
    try: uid = ser.loads(h[7:], max_age=7 * 86400)["id"]
    except (BadSignature, SignatureExpired, KeyError): return None
    return q("SELECT id,name,email,role FROM users WHERE id=?", (uid,), one=True)

def auth(role=None, optional=False):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = current_user()
            if not u and not optional: return err("Please log in", 401)
            if u and role and u["role"] != role: return err("Admin only", 403)
            g.user = dict(u) if u else None
            return f(*a, **k)
        return w
    return deco

def body(): return request.get_json(silent=True) or {}

@app.post("/api/auth/register")
def register():
    b = body(); name, email, pw = (b.get("name") or "").strip(), (b.get("email") or "").strip().lower(), b.get("password") or ""
    if not name or "@" not in email or len(pw) < 4: return err("Enter name, valid email and a password (min 4 chars)")
    if q("SELECT 1 FROM users WHERE email=?", (email,), one=True): return err("Email already registered", 409)
    uid = db().execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'USER')", (name, email, generate_password_hash(pw))).lastrowid
    db().commit()
    return jsonify(token=ser.dumps({"id": uid}), user={"id": uid, "name": name, "email": email, "role": "USER"}), 201

@app.post("/api/auth/login")
def login():
    b = body(); u = q("SELECT * FROM users WHERE email=?", ((b.get("email") or "").strip().lower(),), one=True)
    if not u or not check_password_hash(u["password_hash"], b.get("password") or ""): return err("Invalid email or password", 401)
    return jsonify(token=ser.dumps({"id": u["id"]}), user={k: u[k] for k in ("id", "name", "email", "role")})

@app.get("/api/auth/me")
@auth()
def me(): return jsonify(g.user)

# ---------------------------------------------------------- movies / shows
@app.get("/api/movies")
def movies():
    s = f"%{request.args.get('search', '').strip()}%"
    return jsonify([dict(r) for r in q("SELECT * FROM movies WHERE title LIKE ? OR genre LIKE ? ORDER BY id", (s, s))])

@app.get("/api/movies/<int:mid>")
def movie(mid):
    m = q("SELECT * FROM movies WHERE id=?", (mid,), one=True)
    if not m: return err("Movie not found", 404)
    shows = sorted((dict(r) for r in q(SHOW_SQL + "WHERE sh.movie_id=? AND sh.show_time>?", (mid, now_show()))), key=lambda s: s["show_time"])
    return jsonify(movie=dict(m), shows=shows)

@app.get("/api/shows/<int:sid>")
@auth(optional=True)
def show_detail(sid):
    sh = q(SHOW_SQL + "WHERE sh.id=?", (sid,), one=True)
    if not sh: return err("Show not found", 404)
    uid = g.user["id"] if g.user else None
    mine = {b for b in USER_INDEX.get(uid, []) if BOOKING_INDEX[b]["status"] == "ACTIVE"}
    code = {"AVAILABLE": "A", "BOOKED": "B", "BLOCKED": "X"}
    grid = [["M" if st == "BOOKED" and bid in mine else code[st] for st, bid in row] for row in load_matrix(sid).grid]
    wl = None
    if uid:
        w = q("SELECT * FROM waitlist WHERE user_id=? AND show_id=? AND status='WAITING'", (uid, sid), one=True)
        if w: wl = {"id": w["id"], "seats_wanted": w["seats_wanted"], "position": list(WAITLIST_Q[sid]).index(w["id"]) + 1}
    return jsonify(show=dict(sh), grid=grid, my_waitlist=wl, max_seats=MAX_SEATS)

# --------------------------------------------------------------- booking
@app.post("/api/shows/<int:sid>/book")
@auth()
def book(sid):
    try: picks = sorted({(int(r), int(c)) for r, c in (body().get("seats") or [])})
    except (TypeError, ValueError): return err("Invalid seats")
    if not 1 <= len(picks) <= MAX_SEATS: return err(f"Select 1 to {MAX_SEATS} seats")
    with SHOW_LOCKS[sid]:
        show = q(SHOW_SQL + "WHERE sh.id=?", (sid,), one=True)
        if not show: return err("Show not found", 404)
        if show["show_time"] <= now_show(): return err("This show has already started")
        if any(not (0 <= r < show["n_rows"] and 0 <= c < show["n_cols"]) for r, c in picks): return err("Seat out of range")
        try: bid = create_booking(g.user["id"], show, picks)
        except SeatTaken: return err("Some seats were just taken by someone else. Please pick other seats.", 409)
    return jsonify(booking_view(get_booking(bid))), 201

@app.get("/api/bookings")
@auth()
def my_bookings():
    return jsonify([booking_view(get_booking(i)) for i in sorted(USER_INDEX.get(g.user["id"], []), reverse=True)])

@app.get("/api/bookings/<int:bid>")
@auth()
def one_booking(bid):
    rec = BOOKING_INDEX.get(bid)
    if not rec or (rec["user_id"] != g.user["id"] and g.user["role"] != "ADMIN"): return err("Booking not found", 404)
    return jsonify(booking_view(get_booking(bid)))

@app.post("/api/bookings/<int:bid>/cancel")
@auth()
def cancel(bid):
    rec = BOOKING_INDEX.get(bid)   # O(1) HashMap lookup
    if not rec or (rec["user_id"] != g.user["id"] and g.user["role"] != "ADMIN"): return err("Booking not found", 404)
    sid = rec["show_id"]
    with SHOW_LOCKS[sid]:
        if rec["status"] != "ACTIVE": return err("Booking is already cancelled")
        show = q("SELECT show_time FROM shows WHERE id=?", (sid,), one=True)
        if g.user["role"] != "ADMIN" and show["show_time"] <= now_show(): return err("Cannot cancel after the show has started")
        d = db()
        d.execute("UPDATE bookings SET status='CANCELLED', cancelled_at=? WHERE id=?", (now(), bid))
        d.execute("UPDATE seats SET status='AVAILABLE', booking_id=NULL WHERE booking_id=?", (bid,))
        d.commit(); rec["status"] = "CANCELLED"
        process_waitlist(sid)
    return jsonify(ok=True)

# -------------------------------------------------------------- waitlist
@app.post("/api/shows/<int:sid>/waitlist")
@auth()
def join_waitlist(sid):
    try: n = int(body().get("seats_wanted", 0))
    except (TypeError, ValueError): return err("Invalid seat count")
    if not 1 <= n <= MAX_SEATS: return err(f"Choose 1 to {MAX_SEATS} seats")
    with SHOW_LOCKS[sid]:
        show = q("SELECT show_time FROM shows WHERE id=?", (sid,), one=True)
        if not show: return err("Show not found", 404)
        if show["show_time"] <= now_show(): return err("This show has already started")
        if load_matrix(sid).free_count() >= n: return err("Enough seats are available - please book them directly.")
        if q("SELECT 1 FROM waitlist WHERE user_id=? AND show_id=? AND status='WAITING'", (g.user["id"], sid), one=True):
            return err("You are already on the waitlist for this show", 409)
        wid = db().execute("INSERT INTO waitlist(user_id,show_id,seats_wanted,joined_at) VALUES(?,?,?,?)", (g.user["id"], sid, n, now())).lastrowid
        db().commit(); WAITLIST_Q[sid].append(wid)
        return jsonify(position=len(WAITLIST_Q[sid])), 201

@app.get("/api/waitlist")
@auth()
def my_waitlist():
    out = []
    for w in q("""SELECT w.*, m.title, sh.show_time, sh.screen FROM waitlist w JOIN shows sh ON sh.id=w.show_id
                  JOIN movies m ON m.id=sh.movie_id WHERE w.user_id=? ORDER BY w.id DESC""", (g.user["id"],)):
        d = dict(w); d["position"] = list(WAITLIST_Q[w["show_id"]]).index(w["id"]) + 1 if w["status"] == "WAITING" else None
        out.append(d)
    return jsonify(out)

@app.delete("/api/waitlist/<int:wid>")
@auth()
def leave_waitlist(wid):
    w = q("SELECT * FROM waitlist WHERE id=? AND user_id=? AND status='WAITING'", (wid, g.user["id"]), one=True)
    if not w: return err("Waitlist entry not found", 404)
    with SHOW_LOCKS[w["show_id"]]:
        db().execute("UPDATE waitlist SET status='LEFT' WHERE id=?", (wid,)); db().commit()
        try: WAITLIST_Q[w["show_id"]].remove(wid)
        except ValueError: pass
    return jsonify(ok=True)

@app.get("/api/notifications")
@auth()
def notifications():
    rows = [dict(r) for r in q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],))]
    return jsonify(items=rows, unread=sum(1 for r in rows if not r["is_read"]))

@app.post("/api/notifications/read")
@auth()
def read_notifs():
    db().execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],)); db().commit()
    return jsonify(ok=True)

# ----------------------------------------------------------------- admin
def movie_fields():
    b = body(); title = (b.get("title") or "").strip()
    if not title: return None
    try: return (title, (b.get("genre") or "").strip(), int(b.get("duration") or 0), float(b.get("rating") or 0), (b.get("description") or "").strip())
    except (TypeError, ValueError): return None

@app.post("/api/admin/movies")
@auth("ADMIN")
def add_movie():
    f = movie_fields()
    if not f: return err("Title is required and numbers must be valid")
    mid = db().execute("INSERT INTO movies(title,genre,duration,rating,description) VALUES(?,?,?,?,?)", f).lastrowid; db().commit()
    return jsonify(id=mid), 201

@app.put("/api/admin/movies/<int:mid>")
@auth("ADMIN")
def edit_movie(mid):
    f = movie_fields()
    if not f: return err("Title is required and numbers must be valid")
    db().execute("UPDATE movies SET title=?,genre=?,duration=?,rating=?,description=? WHERE id=?", f + (mid,)); db().commit()
    return jsonify(ok=True)

@app.delete("/api/admin/movies/<int:mid>")
@auth("ADMIN")
def del_movie(mid):
    ids = [r["id"] for r in q("SELECT id FROM shows WHERE movie_id=?", (mid,))]
    for sid in ids:
        if q("SELECT 1 FROM bookings WHERE show_id=? AND status='ACTIVE'", (sid,), one=True):
            return err("Cannot delete: a show of this movie has active bookings")
    for sid in ids: delete_show(sid)
    db().execute("DELETE FROM movies WHERE id=?", (mid,)); db().commit()
    return jsonify(ok=True)

@app.get("/api/admin/shows")
@auth("ADMIN")
def admin_shows():
    return jsonify(sorted((dict(r) for r in q(SHOW_SQL)), key=lambda s: s["show_time"]))

def show_fields(creating):
    b = body()
    try:
        t = datetime.strptime(b.get("show_time", ""), "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M")
        price = float(b.get("price")); screen = (b.get("screen") or "").strip()
        r, c = (int(b.get("n_rows") or 0), int(b.get("n_cols") or 0)) if creating else (0, 0)
        mid = int(b.get("movie_id"))
    except (TypeError, ValueError): return None
    if not screen or price <= 0 or not q("SELECT 1 FROM movies WHERE id=?", (mid,), one=True): return None
    if creating and not (1 <= r <= 15 and 1 <= c <= 20): return None
    return mid, screen, t, price, r, c

@app.post("/api/admin/shows")
@auth("ADMIN")
def add_show():
    f = show_fields(True)
    if not f: return err("Check movie, time, screen, price (>0), rows (1-15) and columns (1-20)")
    return jsonify(id=make_show(*f)), 201

@app.put("/api/admin/shows/<int:sid>")
@auth("ADMIN")
def edit_show(sid):
    f = show_fields(False)
    if not f: return err("Check movie, time, screen and price")
    db().execute("UPDATE shows SET movie_id=?,screen=?,show_time=?,price=? WHERE id=?", f[:4] + (sid,)); db().commit()
    return jsonify(ok=True)

@app.delete("/api/admin/shows/<int:sid>")
@auth("ADMIN")
def del_show(sid):
    with SHOW_LOCKS[sid]:
        if q("SELECT 1 FROM bookings WHERE show_id=? AND status='ACTIVE'", (sid,), one=True):
            return err("Cannot delete: this show has active bookings")
        delete_show(sid)
    return jsonify(ok=True)

@app.post("/api/admin/shows/<int:sid>/seats")
@auth("ADMIN")
def seat_admin(sid):
    b = body(); action = b.get("action")
    if action not in ("block", "unblock"): return err("Invalid action")
    old, new = ("AVAILABLE", "BLOCKED") if action == "block" else ("BLOCKED", "AVAILABLE")
    with SHOW_LOCKS[sid]:
        try:
            for r, c in b.get("seats") or []:
                db().execute("UPDATE seats SET status=? WHERE show_id=? AND seat_row=? AND seat_col=? AND status=?", (new, sid, int(r), int(c), old))
        except (TypeError, ValueError): return err("Invalid seats")
        db().commit()
        if action == "unblock": process_waitlist(sid)
    return jsonify(ok=True)

@app.get("/api/admin/bookings")
@auth("ADMIN")
def admin_bookings():
    s = request.args.get("search", "").strip().lstrip("#")
    if s.isdigit() and int(s) in BOOKING_INDEX: ids = [int(s)]
    elif s:
        like = f"%{s}%"
        ids = sorted((i for u in q("SELECT id FROM users WHERE name LIKE ? OR email LIKE ?", (like, like)) for i in USER_INDEX.get(u["id"], [])), reverse=True)
    else: ids = sorted(BOOKING_INDEX, reverse=True)
    return jsonify([booking_view(get_booking(i)) for i in ids[:200]])

@app.get("/api/admin/stats")
@auth("ADMIN")
def stats():
    one = lambda sql: q(sql, one=True)[0]
    occ = []
    for s in sorted((dict(r) for r in q(SHOW_SQL)), key=lambda s: s["show_time"]):
        tot = s["n_rows"] * s["n_cols"]
        occ.append({"id": s["id"], "title": s["title"], "show_time": s["show_time"], "screen": s["screen"], "booked": s["booked"],
                    "total": tot, "pct": round(100 * s["booked"] / tot) if tot else 0, "waiting": s["waiting"]})
    per_movie = [(r["n"], r["title"]) for r in q("""SELECT m.title, COUNT(*) n FROM seats s JOIN shows sh ON sh.id=s.show_id
                  JOIN movies m ON m.id=sh.movie_id WHERE s.status='BOOKED' GROUP BY m.id""")]
    top = [{"title": t, "seats": n} for n, t in heapq.nlargest(5, per_movie)]   # max-heap ranking
    return jsonify(total_bookings=one("SELECT COUNT(*) FROM bookings WHERE status='ACTIVE'"),
                   revenue=one("SELECT COALESCE(SUM(total),0) FROM bookings WHERE status='ACTIVE'"),
                   cancellations=one("SELECT COUNT(*) FROM bookings WHERE status='CANCELLED'"),
                   waitlist_size=one("SELECT COUNT(*) FROM waitlist WHERE status='WAITING'"),
                   waitlist_fulfilled=one("SELECT COUNT(*) FROM waitlist WHERE status='FULFILLED'"),
                   users=one("SELECT COUNT(*) FROM users WHERE role='USER'"), occupancy=occ, top_movies=top)

# ------------------------------------------------------------------ seed
def seed():
    d = db(); pw = generate_password_hash
    d.executemany("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)", [
        ("Admin", "admin@cinema.com", pw("admin123"), "ADMIN"), ("Aarav", "user@cinema.com", pw("user123"), "USER"),
        ("Riya", "user2@cinema.com", pw("user123"), "USER")])
    d.executemany("INSERT INTO movies(title,genre,duration,rating,description) VALUES(?,?,?,?,?)", [
        ("Inception", "Sci-Fi / Thriller", 148, 8.8, "A thief who steals secrets through dreams gets one last job: planting an idea."),
        ("Interstellar", "Sci-Fi / Drama", 169, 8.7, "Explorers travel through a wormhole in space to ensure humanity's survival."),
        ("Dune: Part Two", "Sci-Fi / Adventure", 166, 8.6, "Paul Atreides unites with the Fremen to take revenge on those who destroyed his family."),
        ("3 Idiots", "Comedy / Drama", 170, 8.4, "Three engineering students chase excellence and friendship over rote learning."),
        ("Kalki 2898 AD", "Sci-Fi / Action", 181, 7.0, "A modern avatar of Vishnu is born in a dystopian future to save the world.")])
    d.commit()
    def t(days, hour):
        x = (datetime.now() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return (x if x > datetime.now() else x + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    ids = [make_show(1, "Screen 1", t(0, 21), 250, 8, 10), make_show(1, "Screen 2", t(1, 14), 220, 6, 8),
           make_show(2, "Screen 1", t(1, 18), 300, 8, 10), make_show(3, "Screen 3", t(1, 20), 350, 8, 12),
           make_show(4, "Screen 2", t(2, 17), 200, 6, 8), make_show(5, "Screen 3", t(2, 21), 280, 8, 10)]
    mini = make_show(1, "Screen 4 (Mini - waitlist demo)", t(1, 22), 150, 2, 4)
    u2 = 3
    for sid, seats in ((ids[0], [(3, 4), (3, 5), (3, 6)]), (ids[2], [(4, 3), (4, 4)])):
        create_booking(u2, q(SHOW_SQL + "WHERE sh.id=?", (sid,), one=True), seats)
    create_booking(u2, q(SHOW_SQL + "WHERE sh.id=?", (mini,), one=True), [(r, c) for r in range(2) for c in range(4)])  # mini show full

def init():
    c = sqlite3.connect(DB_PATH); c.executescript(SCHEMA); c.commit(); c.close()
    with app.app_context():
        if not q("SELECT 1 FROM users LIMIT 1", one=True): seed()
    rebuild_indexes()

init()
if __name__ == "__main__":
    print("CineBook API running on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, threaded=True)
