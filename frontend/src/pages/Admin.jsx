import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt, money } from "../api.js";

export function Dashboard() {
  const [s, setS] = useState(null);
  useEffect(() => { api("/admin/stats").then(setS); }, []);
  if (!s) return <p className="muted">Loading…</p>;
  const cards = [["Active bookings", s.total_bookings], ["Revenue", money(s.revenue)], ["Cancellations", s.cancellations],
    ["Waitlist size", s.waitlist_size], ["Waitlist served", s.waitlist_fulfilled], ["Users", s.users]];
  return (
    <>
      <h1>Dashboard</h1>
      <div className="grid stats">{cards.map(([k, v]) => <div className="card stat" key={k}><span className="muted">{k}</span><b>{v}</b></div>)}</div>
      <div className="row gap top">
        <div className="card grow">
          <h3>Occupancy per show</h3>
          {s.occupancy.map((o) => (
            <div key={o.id} className="occ">
              <div className="row between small"><span>{o.title} · {fmt(o.show_time)} · {o.screen}</span><span>{o.booked}/{o.total} ({o.pct}%){o.waiting > 0 && ` · ${o.waiting} waiting`}</span></div>
              <div className="bar"><div style={{ width: o.pct + "%" }} /></div>
            </div>
          ))}
        </div>
        <div className="card side">
          <h3>Top movies (seats booked)</h3>
          {s.top_movies.map((m, i) => <p key={m.title}>{i + 1}. {m.title} <span className="tag">{m.seats}</span></p>)}
          {!s.top_movies.length && <p className="muted">No bookings yet.</p>}
        </div>
      </div>
    </>
  );
}

const emptyMovie = { title: "", genre: "", duration: 120, rating: 7.5, description: "" };
export function AdminMovies() {
  const [list, setList] = useState([]);
  const [f, setF] = useState(emptyMovie);
  const [editId, setEditId] = useState(null);
  const [err, setErr] = useState("");
  const load = () => api("/movies").then(setList);
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save(e) {
    e.preventDefault(); setErr("");
    try {
      await api(editId ? `/admin/movies/${editId}` : "/admin/movies", { method: editId ? "PUT" : "POST", body: f });
      setF(emptyMovie); setEditId(null); load();
    } catch (x) { setErr(x.message); }
  }
  async function del(id) {
    if (!confirm("Delete this movie and its shows?")) return;
    try { await api(`/admin/movies/${id}`, { method: "DELETE" }); load(); } catch (x) { setErr(x.message); }
  }
  return (
    <>
      <h1>Manage Movies</h1>
      <form className="card form grid2" onSubmit={save}>
        <input placeholder="Title" value={f.title} onChange={set("title")} required />
        <input placeholder="Genre" value={f.genre} onChange={set("genre")} />
        <input type="number" placeholder="Duration (min)" value={f.duration} onChange={set("duration")} />
        <input type="number" step="0.1" placeholder="Rating" value={f.rating} onChange={set("rating")} />
        <textarea placeholder="Description" value={f.description} onChange={set("description")} />
        <div className="row gap"><button className="btn">{editId ? "Update movie" : "Add movie"}</button>
          {editId && <button type="button" className="btn ghost" onClick={() => { setEditId(null); setF(emptyMovie); }}>Cancel edit</button>}</div>
        {err && <p className="error">{err}</p>}
      </form>
      <table><thead><tr><th>ID</th><th>Title</th><th>Genre</th><th>Min</th><th>Rating</th><th /></tr></thead>
        <tbody>{list.map((m) => (
          <tr key={m.id}><td>{m.id}</td><td>{m.title}</td><td>{m.genre}</td><td>{m.duration}</td><td>{m.rating}</td>
            <td className="actions"><button className="btn ghost small" onClick={() => { setEditId(m.id); setF(m); window.scrollTo(0, 0); }}>Edit</button>
              <button className="btn danger small" onClick={() => del(m.id)}>Delete</button></td></tr>))}</tbody></table>
    </>
  );
}

export function AdminShows() {
  const [shows, setShows] = useState([]);
  const [movies, setMovies] = useState([]);
  const [f, setF] = useState({ movie_id: "", screen: "Screen 1", show_time: "", price: 250, n_rows: 8, n_cols: 10 });
  const [err, setErr] = useState("");
  const load = () => { api("/admin/shows").then(setShows); api("/movies").then(setMovies); };
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function add(e) {
    e.preventDefault(); setErr("");
    try { await api("/admin/shows", { method: "POST", body: f }); load(); } catch (x) { setErr(x.message); }
  }
  async function del(id) {
    if (!confirm("Delete this show?")) return;
    try { await api(`/admin/shows/${id}`, { method: "DELETE" }); load(); } catch (x) { setErr(x.message); }
  }
  return (
    <>
      <h1>Manage Shows</h1>
      <form className="card form grid2" onSubmit={add}>
        <select value={f.movie_id} onChange={set("movie_id")} required><option value="">Select movie…</option>
          {movies.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}</select>
        <input placeholder="Screen" value={f.screen} onChange={set("screen")} required />
        <input type="datetime-local" value={f.show_time} onChange={set("show_time")} required />
        <input type="number" placeholder="Price" value={f.price} onChange={set("price")} required />
        <input type="number" placeholder="Rows (1-15)" value={f.n_rows} onChange={set("n_rows")} required />
        <input type="number" placeholder="Seats per row (1-20)" value={f.n_cols} onChange={set("n_cols")} required />
        <button className="btn">Add show</button>
        {err && <p className="error">{err}</p>}
      </form>
      {err && <p className="error">{err}</p>}
      <table><thead><tr><th>Movie</th><th>Time</th><th>Screen</th><th>Price</th><th>Layout</th><th>Booked</th><th>Blocked</th><th>Waiting</th><th /></tr></thead>
        <tbody>{shows.map((s) => (
          <tr key={s.id}><td>{s.title}</td><td>{fmt(s.show_time)}</td><td>{s.screen}</td><td>{money(s.price)}</td><td>{s.n_rows}×{s.n_cols}</td>
            <td>{s.booked}</td><td>{s.blocked}</td><td>{s.waiting}</td>
            <td className="actions"><Link className="btn ghost small" to={`/admin/shows/${s.id}/seats`}>Seats</Link>
              <button className="btn danger small" onClick={() => del(s.id)}>Delete</button></td></tr>))}</tbody></table>
    </>
  );
}

export function AdminBookings() {
  const [list, setList] = useState([]);
  const [s, setS] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api("/admin/bookings?search=" + encodeURIComponent(s)).then(setList);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [s]);
  async function cancel(id) {
    if (!confirm("Cancel this booking?")) return;
    try { await api(`/bookings/${id}/cancel`, { method: "POST" }); load(); } catch (e) { setMsg(e.message); }
  }
  return (
    <>
      <div className="row between"><h1>All Bookings</h1>
        <input className="search" placeholder="Booking ID, user name or email…" value={s} onChange={(e) => setS(e.target.value)} /></div>
      {msg && <p className="error">{msg}</p>}
      <table><thead><tr><th>ID</th><th>User</th><th>Movie</th><th>Show</th><th>Seats</th><th>Total</th><th>Status</th><th /></tr></thead>
        <tbody>{list.map((b) => (
          <tr key={b.id}><td>#{b.id}</td><td>{b.user_name}<br /><span className="muted small">{b.user_email}</span></td><td>{b.title}</td>
            <td>{fmt(b.show_time)}<br /><span className="muted small">{b.screen}</span></td>
            <td>{b.seats.join(", ")}</td><td>{money(b.total)}</td>
            <td><span className={`tag ${b.status === "ACTIVE" ? "ok" : "bad"}`}>{b.status}</span>{b.source === "WAITLIST" && <span className="tag">waitlist</span>}</td>
            <td>{b.status === "ACTIVE" && <button className="btn danger small" onClick={() => cancel(b.id)}>Cancel</button>}</td></tr>))}</tbody></table>
      {!list.length && <p className="muted">No bookings found.</p>}
    </>
  );
}
