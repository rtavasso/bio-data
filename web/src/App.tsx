import { lazy, Suspense } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import type { Health, Participant } from "./api";
import { useInbox } from "./components/workbench/Inbox";
import { ViewBar, ViewSync } from "./components/workbench/ViewBar";
import { routeWithView, useSavedView } from "./savedView";
import type { AccessStanding } from "./types/workbench";
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
const ThreadRead = lazy(() => import("./pages/ThreadRead"));
const Audit = lazy(() => import("./pages/Audit"));

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

// A members-only or private commons (spec v2 V9): say so instead of failing every screen.
function AccessBanner({ access }: { access: AccessStanding | null }) {
  if (!access || access.member || access.read === "public" || access.read === "local") return null;
  return (
    <div className="banner" role="note" aria-label="Access">
      {access.authenticated
        ? <>This commons is private and you are not a member; an operator grants membership.</>
        : <>This commons is readable by its {access.read === "private" ? "granted members" : "members"} only. <Link to="/login">Log in</Link>.</>}
    </div>
  );
}

export default function App() {
  const health = useApi<Health>("/api/health");
  const me = useApi<Participant & { permissions?: string[]; writes_over_http?: boolean }>("/api/me");
  const access = useApi<AccessStanding>("/api/access");
  const view = useSavedView();
  // The person's inbox, live over the per-caller stream (V4); the count shows next to their name.
  const inbox = useInbox(Boolean(me.data?.writes_over_http));
  const operator = Boolean(me.data?.permissions?.includes?.("audit"));
  return (
    <div className="shell">
      <ViewSync />
      <header className="topbar">
        <NavLink to={routeWithView("/board", view)} className="brand">Colloquy</NavLink>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={routeWithView(to, view)}>{label}</NavLink>
          ))}
          {operator && <NavLink to="/audit">Audit</NavLink>}
        </nav>
        <NavLink to={routeWithView("/me", view)} className="me">
          {me.data?.name ?? "me"}
          {inbox.unread > 0 && <span className="wb-badge" aria-label={`${inbox.unread} unread in your inbox`}>{inbox.unread}</span>}
        </NavLink>
      </header>
      <AccessBanner access={access.data} />
      <ViewBar />
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
            <Route path="/thread/:id/read" element={<ThreadRead />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/me" element={<Me />} />
            <Route path="/login" element={<Login />} />
            <Route path="*" element={<Placeholder title="Not found" module="This route" />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
