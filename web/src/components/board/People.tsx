import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, type Participant } from "../../api";
import { short } from "./format";

// One participant listing per page load; participant rows are small and change rarely.
let cache: Promise<Map<string, Participant>> | null = null;

export function loadParticipants(): Promise<Map<string, Participant>> {
  if (!cache) {
    cache = get<{ items: Participant[] }>("/api/participants")
      .then((list) => new Map((list?.items ?? []).map((p) => [p.id, p])))
      .catch((error) => {
        cache = null;
        throw error;
      });
  }
  return cache;
}

export function resetParticipants() {
  cache = null;
}

export function useParticipants(): Map<string, Participant> {
  const [people, setPeople] = useState<Map<string, Participant>>(new Map());
  useEffect(() => {
    let live = true;
    loadParticipants().then((map) => live && setPeople(map)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return people;
}

export function ParticipantLink({ id, name, kind }: { id: string | null | undefined; name?: string; kind?: string }) {
  const people = useParticipants();
  if (!id) return <span className="muted">unknown</span>;
  const known = people.get(id);
  const label = name ?? known?.name ?? short(id);
  const role = kind ?? known?.kind;
  return (
    <Link to={`/agent/${id}`} className="who" title={id}>
      {label}
      {role && role !== "agent" && <span className={`kind kind-${role}`}>{role}</span>}
    </Link>
  );
}
