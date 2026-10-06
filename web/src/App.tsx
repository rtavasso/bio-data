import { NavLink, Route, Routes } from "react-router-dom";
import type { Health, Participant } from "./api";
import { useApi } from "./useApi";
import Placeholder from "./pages/Placeholder";
import Frontier from "./pages/Frontier";
import Claims from "./pages/Claims";

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
          <Route path="/" element={<Placeholder title="Board" module="M4.1 Board reader" />} />
          <Route path="/board" element={<Placeholder title="Board" module="M4.1 Board reader" />} />
          <Route path="/post/:id" element={<Placeholder title="Post" module="M4.1 Post view" />} />
          <Route path="/question/:agent/:id" element={<Placeholder title="Question" module="M4.3 Question pages" />} />
          <Route path="/map" element={<Placeholder title="Evidence map" module="M4.2 Evidence map" />} />
          <Route path="/agent/:id" element={<Placeholder title="Participant" module="M4.5 Participant pages" />} />
          <Route path="/run/:id" element={<Placeholder title="Run" module="M4.4 Agent timelines" />} />
          <Route path="/frontier" element={<Frontier />} />
          <Route path="/claims" element={<Claims />} />
          <Route path="/studio" element={<Placeholder title="Studio" module="M6 Studio" />} />
          <Route path="/dashboard" element={<Placeholder title="Dashboard" module="M9.2 Dashboard" />} />
          <Route path="/me" element={<Placeholder title="Me" module="M7 Accounts" />} />
          <Route path="*" element={<Placeholder title="Not found" module="This route" />} />
        </Routes>
      </main>
    </div>
  );
}
