import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmt, money } from "../api.js";

function Ticket({ b, onCancel }) {
  return (
    <div className="card ticket">
      <div className="row between"><h3>#{b.id} · {b.title}</h3>
        <span className={`tag ${b.status === "ACTIVE" ? "ok" : "bad"}`}>{b.status}</span></div>
      <p className="muted">{fmt(b.show_time)} · {b.screen}</p>
      <p>Seats: <b>{b.seats.join(", ")}</b> · Total: <b>{money(b.total)}</b>{b.source === "WAITLIST" && <span className="tag">via waitlist</span>}</p>
      {onCancel && b.status === "ACTIVE" && <button className="btn danger small" onClick={() => onCancel(b.id)}>Cancel booking</button>}
    </div>
  );
}
export { Ticket };

export function Confirmation() {
  const { id } = useParams();
  const [b, setB] = useState(null);
  useEffect(() => { api(`/bookings/${id}`).then(setB).catch(() => {}); }, [id]);
  if (!b) return <p className="muted">Loading…</p>;
  return (
    <div className="narrow">
      <h1>🎉 Booking confirmed</h1>
      <Ticket b={b} />
      <Link className="btn" to="/my-bookings">My bookings</Link>
    </div>
  );
}

export function MyBookings() {
  const [list, setList] = useState(null);
  const [msg, setMsg] = useState("");
  const load = () => api("/bookings").then(setList);
  useEffect(() => { load(); }, []);
  async function cancel(id) {
    if (!confirm("Cancel this booking? Seats will be released to the waitlist.")) return;
    try { await api(`/bookings/${id}/cancel`, { method: "POST" }); setMsg("Booking cancelled."); load(); }
    catch (e) { setMsg(e.message); }
  }
  if (!list) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>My Bookings</h1>
      {msg && <p className="muted">{msg}</p>}
      {!list.length && <p className="muted">No bookings yet. <Link to="/">Browse movies</Link></p>}
      <div className="grid">{list.map((b) => <Ticket key={b.id} b={b} onCancel={cancel} />)}</div>
    </>
  );
}

export function MyWaitlist() {
  const [list, setList] = useState(null);
  const load = () => api("/waitlist").then(setList);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  if (!list) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>My Waitlist</h1>
      {!list.length && <p className="muted">You haven't joined any waitlist.</p>}
      <div className="grid">
        {list.map((w) => (
          <div className="card" key={w.id}>
            <h3>{w.title}</h3>
            <p className="muted">{fmt(w.show_time)} · {w.screen}</p>
            <p>Seats wanted: <b>{w.seats_wanted}</b> <span className={`tag ${w.status === "FULFILLED" ? "ok" : w.status === "LEFT" ? "bad" : ""}`}>{w.status}</span></p>
            {w.status === "WAITING" && <>
              <p>Queue position: <b>#{w.position}</b></p>
              <button className="btn danger small" onClick={async () => { await api(`/waitlist/${w.id}`, { method: "DELETE" }); load(); }}>Leave queue</button>
            </>}
            {w.status === "FULFILLED" && <Link to="/my-bookings">See booking →</Link>}
          </div>
        ))}
      </div>
    </>
  );
}

export function Notifications() {
  const [d, setD] = useState(null);
  useEffect(() => { api("/notifications").then((x) => { setD(x); if (x.unread) api("/notifications/read", { method: "POST" }); }); }, []);
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>Notifications</h1>
      {!d.items.length && <p className="muted">Nothing yet. You'll be notified when a waitlist seat is allotted.</p>}
      {d.items.map((n) => (
        <div className={`card note ${n.is_read ? "" : "unread"}`} key={n.id}><p>{n.message}</p><span className="muted small">{fmt(n.created_at)}</span></div>
      ))}
    </>
  );
}
