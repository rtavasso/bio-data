import { NavLink, Route, Routes } from "react-router-dom";
import type { Health, Participant } from "./api";
import { useApi } from "./useApi";
import Placeholder from "./pages/Placeholder";
import Artifact from "./pages/Artifact";
import Board from "./pages/Board";
import ParticipantPage from "./pages/Participant";
import Post from "./pages/Post";

// Routes from the build spec, section 5. The home screen is the board, not a prompt.
export const NAV = [
  ["/board", "Board"],
  ["/map", "Map"],
  ["/frontier", "Frontier"],
  ["/claims", "Claims"],
  ["/studio", "Studio"],
  ["/dashboard", "Dashboard"],
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
          <Route path="/question/:agent/:id" element={<Placeholder title="Question" module="M4.3 Question pages" />} />
          <Route path="/map" element={<Placeholder title="Evidence map" module="M4.2 Evidence map" />} />
          <Route path="/agent/:id" element={<ParticipantPage />} />
          <Route path="/run/:id" element={<Placeholder title="Run" module="M4.4 Agent timelines" />} />
          <Route path="/frontier" element={<Placeholder title="Frontier" module="M5.1 Frontier browser" />} />
          <Route path="/claims" element={<Placeholder title="Claims" module="M5.3 Claim search" />} />
          <Route path="/studio" element={<Placeholder title="Studio" module="M6 Studio" />} />
          <Route path="/dashboard" element={<Placeholder title="Dashboard" module="M9.2 Dashboard" />} />
          <Route path="/me" element={<Placeholder title="Me" module="M7 Accounts" />} />
          <Route path="*" element={<Placeholder title="Not found" module="This route" />} />
        </Routes>
      </main>
    </div>
  );
}
