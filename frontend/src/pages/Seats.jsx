import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmt, money, seatLabel, useAuth } from "../api.js";

export function SeatGrid({ grid, selected, onToggle, admin }) {
  return (
    <div className="seatmap">
      <div className="screen">SCREEN</div>
      {grid.map((row, r) => (
        <div className="seatrow" key={r}>
          <span className="rl">{String.fromCharCode(65 + r)}</span>
          {row.map((st, c) => {
            const key = `${r},${c}`;
            const clickable = st === "A" || (admin && st === "X");
            return (
              <button key={c} disabled={!clickable} title={seatLabel(r, c)}
                className={`seat ${selected.includes(key) ? "S" : st}`} onClick={() => onToggle(key)}>{c + 1}</button>
            );
          })}
        </div>
      ))}
      <div className="legend">
        <span><i className="seat A" />Available</span><span><i className="seat S" />Selected</span>
        <span><i className="seat B" />Booked</span><span><i className="seat M" />Your booking</span><span><i className="seat X" />Blocked</span>
      </div>
    </div>
  );
}

function useShow(id) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState([]);
  const load = useCallback(() => api(`/shows/${id}`).then((x) => {
    setD(x); setErr("");
    setSel((s) => s.filter((k) => { const [r, c] = k.split(","); return ["A", "X"].includes(x.grid[r]?.[c]); }));
  }).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);
  const toggle = (k, max = 99) => setSel((s) => s.includes(k) ? s.filter((x) => x !== k) : s.length < max ? [...s, k] : s);
  return { d, err, sel, setSel, toggle, load };
}

export default function Seats() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const { d, err, sel, setSel, toggle, load } = useShow(id);
  const [msg, setMsg] = useState("");
  const [n, setN] = useState(2);
  if (err && !d) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const { show: s, grid, my_waitlist: wl, max_seats: max } = d;
  const free = grid.flat().filter((x) => x === "A").length;
  const labels = sel.map((k) => seatLabel(...k.split(",")));

  async function book() {
    if (!user) return nav("/login");
    setMsg("");
    try {
      const b = await api(`/shows/${id}/book`, { method: "POST", body: { seats: sel.map((k) => k.split(",").map(Number)) } });
      nav(`/booking/${b.id}`);
    } catch (e) { setMsg(e.message); setSel([]); load(); }
  }
  async function join() {
    if (!user) return nav("/login");
    setMsg("");
    try { await api(`/shows/${id}/waitlist`, { method: "POST", body: { seats_wanted: n } }); load(); }
    catch (e) { setMsg(e.message); }
  }
  async function leave() { await api(`/waitlist/${wl.id}`, { method: "DELETE" }); load(); }

  return (
    <>
      <h1>{s.title}</h1>
      <p className="muted">{fmt(s.show_time)} · {s.screen} · {money(s.price)} / seat · {free} free · {s.waiting} waiting</p>
      <div className="row gap top">
        <div className="card grow"><SeatGrid grid={grid} selected={sel} onToggle={(k) => toggle(k, max)} /></div>
        <div className="side">
          <div className="card">
            <h3>Your selection</h3>
            {sel.length ? <><p><b>{labels.join(", ")}</b></p><p>Total: <b>{money(sel.length * s.price)}</b></p></> : <p className="muted">Pick up to {max} seats.</p>}
            <button className="btn" disabled={!sel.length} onClick={book}>Book {sel.length || ""} seat(s)</button>
          </div>
          <div className="card">
            <h3>Waitlist</h3>
            {wl ? (
              <>
                <p>You're <b>#{wl.position}</b> in the queue for <b>{wl.seats_wanted}</b> seat(s).</p>
                <p className="muted">Seats are auto-booked for you when a cancellation frees enough.</p>
                <button className="btn danger" onClick={leave}>Leave waitlist</button>
              </>
            ) : (
              <>
                <p className="muted">Not enough seats? Join the queue and get seats automatically when someone cancels.</p>
                <label>Seats wanted <select value={n} onChange={(e) => setN(+e.target.value)}>
                  {Array.from({ length: max }, (_, i) => <option key={i + 1}>{i + 1}</option>)}</select></label>
                <button className="btn" disabled={free >= n} onClick={join}>Join waitlist</button>
                {free >= n && <p className="muted small">{free} seats are free - book directly.</p>}
              </>
            )}
          </div>
          {msg && <p className="error">{msg}</p>}
        </div>
      </div>
    </>
  );
}

export function AdminSeats() {
  const { id } = useParams();
  const { d, err, sel, setSel, toggle, load } = useShow(id);
  if (err && !d) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const act = async (action) => {
    await api(`/admin/shows/${id}/seats`, { method: "POST", body: { action, seats: sel.map((k) => k.split(",").map(Number)) } });
    setSel([]); load();
  };
  return (
    <>
      <Link to="/admin/shows">← Back to shows</Link>
      <h1>Seat management: {d.show.title}</h1>
      <p className="muted">{fmt(d.show.show_time)} · {d.show.screen} · {d.show.booked} booked · {d.show.blocked} blocked · {d.show.waiting} waiting</p>
      <div className="card">
        <SeatGrid grid={d.grid} selected={sel} onToggle={toggle} admin />
        <div className="row gap">
          <button className="btn danger" disabled={!sel.length} onClick={() => act("block")}>Block selected</button>
          <button className="btn" disabled={!sel.length} onClick={() => act("unblock")}>Unblock selected</button>
        </div>
        <p className="muted small">Select available seats to block, or blocked seats to unblock (unblocking serves the waitlist). Booked seats can't be changed here.</p>
      </div>
    </>
  );
}
