import { Link } from "react-router-dom";
import type { ThreadNode } from "../../types/board";
import { Badge, KindBadge } from "./Badges";
import { ParticipantLink } from "./People";
import { when } from "./format";

function nameOf(node: ThreadNode) {
  return "name" in node.author ? node.author.name : undefined;
}

// Nested reply tree; corrections sit inline under the post they supersede and are marked as such.
export function ThreadTree({ node, focus }: { node: ThreadNode; focus?: string }) {
  const corrected = node.superseded_by.length > 0;
  return (
    <li className={`tree-node${node.id === focus ? " focus" : ""}${node.corrects ? " correction" : ""}`}>
      <div className="tree-line">
        {node.id === focus ? (
          <strong aria-current="true">{node.hidden ? "Hidden post" : node.title}</strong>
        ) : (
          <Link to={`/post/${node.id}`}>{node.hidden ? "Hidden post" : node.title}</Link>
        )}{" "}
        <KindBadge kind={node.kind} />
        {node.corrects && <Badge tone="accent">corrects earlier post</Badge>}
        {corrected && <Badge tone="warn">superseded</Badge>}{" "}
        <span className="meta">
          <ParticipantLink id={node.author.id} name={nameOf(node)} /> · {when(node.created)}
        </span>
      </div>
      {(node.children.length > 0 || node.corrections.length > 0) && (
        <ul>
          {node.corrections.map((child) => <ThreadTree key={child.id} node={child} focus={focus} />)}
          {node.children.map((child) => <ThreadTree key={child.id} node={child} focus={focus} />)}
        </ul>
      )}
    </li>
  );
}
