import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useAuth } from "../api.js";

export default function Auth() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault(); setErr("");
    try {
      const d = await api(`/auth/${mode}`, { method: "POST", body: f });
      login(d.token, d.user);
      nav(d.user.role === "ADMIN" ? "/admin" : "/");
    } catch (x) { setErr(x.message); }
  }
  return (
    <div className="card narrow">
      <h2>{mode === "login" ? "Login" : "Create account"}</h2>
      <form onSubmit={submit} className="form">
        {mode === "register" && <input placeholder="Full name" value={f.name} onChange={set("name")} required />}
        <input type="email" placeholder="Email" value={f.email} onChange={set("email")} required />
        <input type="password" placeholder="Password" value={f.password} onChange={set("password")} required />
        {err && <p className="error">{err}</p>}
        <button className="btn">{mode === "login" ? "Login" : "Register"}</button>
      </form>
      <p className="muted">
        {mode === "login" ? "New here? " : "Have an account? "}
        <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
          {mode === "login" ? "Register" : "Login"}
        </a>
      </p>
      {mode === "login" && (
        <div className="demo">
          <b>Demo accounts</b> (click to fill)
          {[["Admin", "admin@cinema.com", "admin123"], ["User 1", "user@cinema.com", "user123"], ["User 2", "user2@cinema.com", "user123"]].map(([n, e, p]) => (
            <button key={e} type="button" className="btn ghost small" onClick={() => setF({ ...f, email: e, password: p })}>{n}</button>
          ))}
        </div>
      )}
    </div>
  );
}
