import { Link } from "react-router-dom";
import { Untrusted } from "../Untrusted";
import { PromoteForm } from "../participation/Actions";
import { Datasets, StatusBadge, Toggle, defaultTaskType } from "./Ledger";
import { KIND_LABELS, type BoardCard, type BoardColumn, type FrontierBoardView, type RequestInfo, type SharedExperiment } from "../../types/ledger";

// V5: the frontier as the planning surface. Items and shared experiments by board column (open, blocked,
// candidate evidence, promoted, closed) with the request each promotion created (target, budget, state), per-column
// budget totals and targets, and the reader's allowance. Promotion from a card is the ordinary attributed write;
// "blocked" is an open item whose author recorded a blocker, not a state anyone sets.

function budgetText(budget?: Record<string, number> | null): string {
  const parts = Object.entries(budget ?? {}).map(([k, v]) => `${v} ${k.replace("_", " ")}`);
  return parts.length ? parts.join(", ") : "no budget";
}

function RequestLine({ request }: { request: RequestInfo }) {
  return (
    <p className="board-request" aria-label="Promotion request">
      <span className="ledger-badge">{request.task_type ?? "request"}</span>{" "}
      for <Link to={`/agent/${request.target}`}>{request.target_name}</Link> · {budgetText(request.budget)}
      {request.deadline && <> · due {request.deadline.slice(0, 10)}</>} · <span className="mono">{request.state}</span>
      {request.answer && <> · <Link to={`/post/${request.answer}`}>answer</Link></>}
    </p>
  );
}

function ItemCard({ card, onDone }: { card: BoardCard; onDone: () => void }) {
  const promotable = card.column !== "promoted" && card.column !== "closed";
  return (
    <article className={`board-card${card.status === "withdrawn" ? " withdrawn" : ""}`} aria-label={`Card ${card.id}`}>
      <header className="ledger-card-head">
        <span className="ledger-badge">{KIND_LABELS[card.kind]}</span>
        {card.column === "closed" && <StatusBadge status={card.status} />}
        {card.candidate_evidence && <span className="ledger-badge set-by">{card.candidate_evidence.set_by}</span>}
      </header>
      <Untrusted author={card.author_name ?? card.author}>
        <p className="ledger-text">{card.text}</p>
        {card.blocked_by && <p className="muted">Blocked by: {card.blocked_by}</p>}
      </Untrusted>
      <p className="muted small">
        <Link to={`/question/${card.author}/${card.question}`}>{card.question_title ?? card.question}</Link>
      </p>
      <Datasets item={card} />
      {card.request && <RequestLine request={card.request} />}
      {promotable && (
        <footer className="ledger-actions">
          <Toggle label="Promote">
            <PromoteForm sourceKind="frontier_item" sourceId={card.id} defaultTarget={card.author}
              defaultTaskType={defaultTaskType(card)} onDone={onDone} />
          </Toggle>
        </footer>
      )}
    </article>
  );
}

function ExperimentCard({ experiment, onDone }: { experiment: SharedExperiment; onDone: () => void }) {
  const active = experiment.request && ["pending", "running"].includes(experiment.request.state);
  return (
    <article className="board-card board-experiment" aria-label={`Shared experiment ${experiment.id}`}>
      <header className="ledger-card-head">
        <span className="ledger-badge status-promoted">shared experiment</span>
        <span className="muted small">{experiment.questions.length} questions</span>
      </header>
      <p className="ledger-text">{experiment.text}</p>
      <ul className="board-members" aria-label="Member questions">
        {experiment.items.map((m) => (
          <li key={m.id}>
            {m.present ? (
              <Link to={`/question/${m.author}/${m.question}`}>{m.question_title ?? m.question}</Link>
            ) : <span className="mono">{m.id}</span>}
            {m.status && <> <StatusBadge status={m.status} /></>}
          </li>
        ))}
      </ul>
      <p className="muted small">{experiment.note}</p>
      {experiment.request && <RequestLine request={experiment.request} />}
      {experiment.column !== "closed" && !active && (
        <footer className="ledger-actions">
          <Toggle label="Promote">
            <PromoteForm sourceKind="shared_experiment" sourceId={experiment.id} onDone={onDone} />
          </Toggle>
        </footer>
      )}
    </article>
  );
}

function Column({ column, onDone }: { column: BoardColumn; onDone: () => void }) {
  return (
    <section className="board-column" aria-label={`${column.label} column`}>
      <header className="board-column-head">
        <h2>{column.label} <span className="muted">({column.count})</span></h2>
        {column.requests > 0 && (
          <p className="muted small">
            {column.requests} request{column.requests === 1 ? "" : "s"} · budget {budgetText(column.budget)} · targets{" "}
            {column.targets.map((t) => `${t.name} (${t.requests})`).join(", ")}
          </p>
        )}
        {column.withdrawn ? <p className="muted small">{column.withdrawn} withdrawn by their authors</p> : null}
      </header>
      {column.experiments.map((e) => <ExperimentCard key={e.id} experiment={e} onDone={onDone} />)}
      {column.items.map((c) => <ItemCard key={c.id} card={c} onDone={onDone} />)}
    </section>
  );
}

export function FrontierBoard({ view, onDone }: { view: FrontierBoardView; onDone: () => void }) {
  const allowance = view.allowance;
  return (
    <>
      <p className="muted">
        {view.total} item{view.total === 1 ? "" : "s"}, {view.experiments} shared experiment{view.experiments === 1 ? "" : "s"}. {view.policy}
      </p>
      {allowance && (
        <p className="muted small" aria-label="Your allowance">
          Your allowance: {allowance.unlimited ? "unlimited" : allowance.configured === false
            ? "none configured (promotions are refused until an operator sets one)"
            : `${budgetText(allowance.remaining)} remaining of ${budgetText(allowance.allowance)}`}.
        </p>
      )}
      <div className="board-columns">
        {view.columns.map((c) => <Column key={c.key} column={c} onDone={onDone} />)}
      </div>
    </>
  );
}
