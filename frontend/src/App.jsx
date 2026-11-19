import { useEffect, useState, useCallback } from "react";
import { Routes, Route, NavLink, Navigate, Link, useNavigate, useLocation } from "react-router-dom";
import { api, AuthCtx, useAuth } from "./api.js";
import Auth from "./pages/Auth.jsx";
import Home from "./pages/Home.jsx";
import Movie from "./pages/Movie.jsx";
import Seats, { AdminSeats } from "./pages/Seats.jsx";
import { Confirmation, MyBookings, MyWaitlist, Notifications } from "./pages/Account.jsx";
import { Dashboard, AdminMovies, AdminShows, AdminBookings } from "./pages/Admin.jsx";

function Guard({ admin, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (admin && user.role !== "ADMIN") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [unread, setUnread] = useState(0);
  const nav = useNavigate();
  const loc = useLocation();

  useEffect(() => {
    if (!localStorage.getItem("token")) { setReady(true); return; }
    api("/auth/me").then(setUser).catch(() => localStorage.removeItem("token")).finally(() => setReady(true));
  }, []);

  const refreshUnread = useCallback(() => {
    if (user && user.role === "USER") api("/notifications").then((d) => setUnread(d.unread)).catch(() => {});
  }, [user]);
  useEffect(() => { refreshUnread(); }, [loc.pathname, refreshUnread]);
  useEffect(() => { const t = setInterval(refreshUnread, 10000); return () => clearInterval(t); }, [refreshUnread]);

  const login = (token, u) => { localStorage.setItem("token", token); setUser(u); };
  const logout = () => { localStorage.removeItem("token"); setUser(null); setUnread(0); nav("/"); };
  if (!ready) return <p className="center">Loading…</p>;

  return (
    <AuthCtx.Provider value={{ user, login, logout, refreshUnread }}>
      <header className="nav">
        <Link to="/" className="brand">🎬 CineBook</Link>
        <nav>
          {user?.role === "ADMIN" ? (
            <>
              <NavLink to="/admin" end>Dashboard</NavLink>
              <NavLink to="/admin/movies">Movies</NavLink>
              <NavLink to="/admin/shows">Shows</NavLink>
              <NavLink to="/admin/bookings">Bookings</NavLink>
            </>
          ) : (
            <>
              <NavLink to="/" end>Movies</NavLink>
              {user && <>
                <NavLink to="/my-bookings">My Bookings</NavLink>
                <NavLink to="/my-waitlist">Waitlist</NavLink>
                <NavLink to="/notifications">Notifications{unread > 0 && <span className="badge">{unread}</span>}</NavLink>
              </>}
            </>
          )}
        </nav>
        <div className="right">
          {user ? <><span className="muted">{user.name} ({user.role})</span><button className="btn ghost" onClick={logout}>Logout</button></>
                : <Link className="btn" to="/login">Login</Link>}
        </div>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Auth />} />
          <Route path="/movies/:id" element={<Movie />} />
          <Route path="/shows/:id" element={<Seats />} />
          <Route path="/booking/:id" element={<Guard><Confirmation /></Guard>} />
          <Route path="/my-bookings" element={<Guard><MyBookings /></Guard>} />
          <Route path="/my-waitlist" element={<Guard><MyWaitlist /></Guard>} />
          <Route path="/notifications" element={<Guard><Notifications /></Guard>} />
          <Route path="/admin" element={<Guard admin><Dashboard /></Guard>} />
          <Route path="/admin/movies" element={<Guard admin><AdminMovies /></Guard>} />
          <Route path="/admin/shows" element={<Guard admin><AdminShows /></Guard>} />
          <Route path="/admin/shows/:id/seats" element={<Guard admin><AdminSeats /></Guard>} />
          <Route path="/admin/bookings" element={<Guard admin><AdminBookings /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </AuthCtx.Provider>
  );
}
