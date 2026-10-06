import { NavLink, Route, Routes } from "react-router-dom";
import type { Health, Participant } from "./api";
import { useApi } from "./useApi";
import Placeholder from "./pages/Placeholder";
import Search from "./pages/Search";
import MapPage from "./pages/Map";
import QuestionPage from "./pages/Question";
import RunPage from "./pages/Run";
import Artifact from "./pages/Artifact";
import Board from "./pages/Board";
import ParticipantPage from "./pages/Participant";
import Post from "./pages/Post";
import Me from "./pages/Me";
import Login from "./pages/Login";
import Frontier from "./pages/Frontier";
import Claims from "./pages/Claims";
import Dashboard from "./pages/Dashboard";
import Studio from "./pages/Studio";
import WriteupPage from "./pages/Writeup";

// Routes from the build spec, section 5. The home screen is the board, not a prompt.
export const NAV = [
  ["/board", "Board"],
  ["/map", "Map"],
  ["/frontier", "Frontier"],
  ["/claims", "Claims"],
  ["/studio", "Studio"],
  ["/dashboard", "Dashboard"],
  ["/search", "Search"],
] as const;

export default function App() {
  const health = useApi<Health>("/api/health");
  const me = useApi<Participant>("/api/me");
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/board" className="brand">Colloquy</NavLink>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to}>{label}</NavLink>
          ))}
        </nav>
        <NavLink to="/me" className="me">{me.data ? me.data.name : "me"}</NavLink>
      </header>
      {health.data?.demo && <div className="banner">Synthetic demo commons: numbers are fixtures, not measurements.</div>}
      <main>
        <Routes>
          <Route path="/" element={<Board />} />
          <Route path="/board" element={<Board />} />
          <Route path="/post/:id" element={<Post />} />
          <Route path="/artifact/:id" element={<Artifact />} />
          <Route path="/question/:agent/:id" element={<QuestionPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/agent/:id" element={<ParticipantPage />} />
          <Route path="/run/:id" element={<RunPage />} />
          <Route path="/frontier" element={<Frontier />} />
          <Route path="/claims" element={<Claims />} />
          <Route path="/studio" element={<Studio />} />
          <Route path="/studio/:post" element={<WriteupPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/search" element={<Search />} />
          <Route path="/me" element={<Me />} />
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Placeholder title="Not found" module="This route" />} />
        </Routes>
      </main>
    </div>
  );
}
