import { lazy, Suspense } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import type { Health, Participant } from "./api";
import { useApi } from "./useApi";
import Placeholder from "./pages/Placeholder";

// Each screen is its own chunk, loaded when its route is first visited.
const Search = lazy(() => import("./pages/Search"));
const MapPage = lazy(() => import("./pages/Map"));
const QuestionPage = lazy(() => import("./pages/Question"));
const Questions = lazy(() => import("./pages/Questions"));
const QuestionById = lazy(() => import("./pages/Questions").then((m) => ({ default: m.QuestionById })));
const RunPage = lazy(() => import("./pages/Run"));
const Artifact = lazy(() => import("./pages/Artifact"));
const Board = lazy(() => import("./pages/Board"));
const ParticipantPage = lazy(() => import("./pages/Participant"));
const Post = lazy(() => import("./pages/Post"));
const Me = lazy(() => import("./pages/Me"));
const Login = lazy(() => import("./pages/Login"));
const Frontier = lazy(() => import("./pages/Frontier"));
const Claims = lazy(() => import("./pages/Claims"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Studio = lazy(() => import("./pages/Studio"));
const WriteupPage = lazy(() => import("./pages/Writeup"));

// Routes from the build spec, section 5. The home screen is the board, not a prompt.
export const NAV = [
  ["/board", "Board"],
  ["/question", "Questions"],
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
        <Suspense fallback={<p className="muted" role="status">Loading…</p>}>
          <Routes>
            <Route path="/" element={<Board />} />
            <Route path="/board" element={<Board />} />
            <Route path="/post/:id" element={<Post />} />
            <Route path="/artifact/:id" element={<Artifact />} />
            <Route path="/question" element={<Questions />} />
            <Route path="/question/:id" element={<QuestionById />} />
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
        </Suspense>
      </main>
    </div>
  );
}
