import { Link, useParams } from "react-router-dom";
import { withBase } from "../base";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import type { Tour as TourData, TourListing, TourStep } from "../types/publishing";
import { useApi } from "../useApi";
import "./publishing.css";

// Spec v2 V3: a curated reading path for a visitor, board -> one thread -> one number -> its bytes. Every step
// is re-checked by the server against the archive on each request; a broken step is shown as broken, never as
// verified. The curated pointer is the curator's reading aid, not the post author's pointer.

function short(id: string) {
  return id.length > 22 ? `${id.slice(0, 18)}…` : id;
}

function Excerpt({ step }: { step: TourStep }) {
  const n = step.number;
  if (!n) return null;
  const { text, number_at: at, number_length: length } = n.excerpt;
  const route = step.clicks?.[0]?.to;
  const number = text.slice(at, at + length);
  return (
    <Untrusted author={step.post?.author}>
      <p className="tour-excerpt">
        {n.excerpt.clipped && "… "}{text.slice(0, at)}
        {route && step.ok ? (
          <Link to={route} className="tour-number" aria-label={`Number ${number}: open its cited bytes`}>{number}</Link>
        ) : <mark className="tour-number broken">{number}</mark>}
        {text.slice(at + length)}{n.excerpt.clipped && " …"}
      </p>
      <p className="meta">line {n.excerpt.line} of the post</p>
    </Untrusted>
  );
}

function Verification({ step }: { step: TourStep }) {
  const info = step.artifact_info;
  if (!info) return null;
  const found = info.verification.found as Record<string, unknown> | undefined;
  const where = found ? (found.key !== undefined ? `key ${String(found.key)}` : found.column !== undefined
    ? `row ${String(found.row)}, column ${String(found.column)}` : found.line !== undefined ? `line ${String(found.line)}` : "") : "";
  return (
    <p className="meta">
      {info.verification.result === "verified"
        ? <>Value at the locator: <span className="mono">{String(found?.value)}</span> ({where}), verified against the output bytes.</>
        : <span className="error">Not verified: {info.verification.reason ?? "no match"}</span>}
      {" "}Checker status of this number on the post: <span className="mono">{step.number?.checker_status ?? "not detected"}</span>
      {step.number?.checker_status === "post_scoped" && " (the author named the artifact for the post, not this number)"}.
    </p>
  );
}

function Step({ step }: { step: TourStep }) {
  const bytes = step.clicks?.[1]?.to;
  return (
    <li className={`panel tour-step ${step.ok ? "" : "tour-broken"}`} aria-label={`Step ${step.step}`}>
      <ol className="tour-path">
        <li><Link to="/board">Board</Link></li>
        <li>Thread: {step.thread ? <Link to={step.thread.route}>{step.thread.title ?? short(step.thread.root)}</Link> : "—"}
          {step.thread && <span className="muted small"> ({step.thread.posts} posts)</span>}</li>
        <li>Final: {step.post?.route ? <Link to={step.post.route}>{step.post.title ?? short(step.final)}</Link> : short(step.final)}</li>
        <li>Number → bytes: click the number (1), then the bytes link on the artifact page (2)</li>
      </ol>
      <Excerpt step={step} />
      <Verification step={step} />
      {step.ok && step.clicks && (
        <p className="meta">
          <Link to={step.clicks[0].to}>Cited location</Link> (click 1) ·{" "}
          {bytes && <a href={withBase(bytes)} target="_blank" rel="noopener noreferrer">raw bytes</a>} (click 2) ·{" "}
          <span className="mono">{step.artifact_info?.name ?? short(step.artifact)}</span> · <span className="mono">#{step.locator}</span>
        </p>
      )}
      {step.note && <p className="tour-note"><span className="muted">Curator's note:</span> {step.note}</p>}
      {!step.ok && (
        <div className="error" role="alert">
          <strong>Broken step.</strong>
          <ul>{step.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}
    </li>
  );
}

export function TourView({ name }: { name: string }) {
  const state = useApi<TourData>(`/api/tours/${encodeURIComponent(name)}`);
  const tour = state.data;
  if (!tour) return <Status state={state} />;
  return (
    <section className="tour" aria-labelledby="tour-title">
      <h1 id="tour-title">{tour.title}</h1>
      {tour.intro && <p>{tour.intro}</p>}
      <p className="muted">
        Curated by {tour.curator.name}. {tour.curator.note} {tour.summary.ok} of {tour.summary.steps} steps verified now;
        {" "}{tour.summary.finals_reaching_bytes_in_two_clicks} finals reach their bytes in two clicks from a number.
      </p>
      {!tour.applies && <p className="error">This tour does not apply to this commons: none of its posts is on this board.</p>}
      <p className="withheld-notice">
        Curated pointers are the curator's reading aid. The authors named these artifacts for their posts; the curator
        located each number's value and the commons' checker re-verifies it against the bytes on every visit.
      </p>
      <ol className="tour-steps">{tour.steps.map((s) => <Step key={s.step} step={s} />)}</ol>
    </section>
  );
}

export default function TourPage() {
  const { name } = useParams();
  const listing = useApi<TourListing>(name ? null : "/api/tours");
  if (name) return <TourView name={name} />;
  const tours = listing.data?.tours ?? [];
  const applicable = tours.filter((t) => t.applies);
  if (!listing.data) return <Status state={listing} />;
  if (applicable.length === 1) return <TourView name={applicable[0].name} />;
  return (
    <section className="tour" aria-labelledby="tours-title">
      <h1 id="tours-title">Tours</h1>
      {applicable.length === 0 && <p className="muted">No curated tour applies to this commons.</p>}
      <ul>
        {tours.map((t) => (
          <li key={t.name}>
            <Link to={`/tour/${t.name}`}>{t.title}</Link>{" "}
            <span className="muted small">by {t.curator.name} · {t.applies ? `${t.summary.ok}/${t.summary.steps} steps verified` : "does not apply here"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
