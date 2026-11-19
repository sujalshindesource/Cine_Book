import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export const poster = (id) => ({ background: `linear-gradient(135deg, hsl(${(id * 67) % 360} 70% 38%), hsl(${(id * 67 + 50) % 360} 60% 18%))` });

export default function Home() {
  const [movies, setMovies] = useState([]);
  const [s, setS] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    const t = setTimeout(() => api("/movies?search=" + encodeURIComponent(s)).then(setMovies).catch((e) => setErr(e.message)), 250);
    return () => clearTimeout(t);
  }, [s]);
  return (
    <>
      <div className="row between"><h1>Now Showing</h1>
        <input className="search" placeholder="Search by title or genre…" value={s} onChange={(e) => setS(e.target.value)} /></div>
      {err && <p className="error">{err}</p>}
      <div className="grid">
        {movies.map((m) => (
          <Link to={`/movies/${m.id}`} className="card movie" key={m.id}>
            <div className="poster" style={poster(m.id)}>{m.title[0]}</div>
            <h3>{m.title}</h3>
            <p className="muted">{m.genre} · {m.duration} min</p>
            <span className="tag">★ {m.rating}</span>
          </Link>
        ))}
      </div>
      {!movies.length && !err && <p className="muted">No movies found.</p>}
    </>
  );
}
