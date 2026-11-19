import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmt, money } from "../api.js";
import { poster } from "./Home.jsx";

export default function Movie() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api(`/movies/${id}`).then(setD).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const { movie: m, shows } = d;
  return (
    <>
      <div className="card row gap">
        <div className="poster big" style={poster(m.id)}>{m.title[0]}</div>
        <div><h1>{m.title}</h1><p className="muted">{m.genre} · {m.duration} min · ★ {m.rating}</p><p>{m.description}</p></div>
      </div>
      <h2>Show timings</h2>
      {!shows.length && <p className="muted">No upcoming shows.</p>}
      <div className="grid">
        {shows.map((s) => (
          <div className="card" key={s.id}>
            <h3>{fmt(s.show_time)}</h3>
            <p className="muted">{s.screen} · {money(s.price)} / seat</p>
            <p>{s.free > 0 ? <span className="tag ok">{s.free} seats free</span> : <span className="tag bad">Sold out</span>}
              {s.waiting > 0 && <span className="tag">{s.waiting} on waitlist</span>}</p>
            <Link className="btn" to={`/shows/${s.id}`}>{s.free > 0 ? "Select seats" : "View / join waitlist"}</Link>
          </div>
        ))}
      </div>
    </>
  );
}
