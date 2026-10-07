import { Link } from "react-router-dom";
import { isWithheld, type ThreadNode } from "../../types/board";
import { Badge, KindBadge } from "./Badges";
import { ParticipantLink } from "./People";
import { when } from "./format";

function Branches({ node, focus }: { node: ThreadNode; focus?: string }) {
  if (node.children.length === 0 && node.corrections.length === 0) return null;
  return (
    <ul>
      {node.corrections.map((child) => <ThreadTree key={child.id} node={child} focus={focus} />)}
      {node.children.map((child) => <ThreadTree key={child.id} node={child} focus={focus} />)}
    </ul>
  );
}

// Nested reply tree; corrections sit inline under the post they supersede and are marked as such.
// A hidden post is a placeholder (identity only); its replies stay in place under it.
export function ThreadTree({ node, focus }: { node: ThreadNode; focus?: string }) {
  if (isWithheld(node)) {
    return (
      <li className={`tree-node hidden-node${node.id === focus ? " focus" : ""}`}>
        <div className="tree-line">
          {node.id === focus ? <strong aria-current="true">Hidden post</strong>
            : <Link to={`/post/${node.id}`}>Hidden post</Link>}{" "}
          <span className="meta">hidden by moderation</span>
        </div>
        <Branches node={node} focus={focus} />
      </li>
    );
  }
  const corrected = node.superseded_by.length > 0;
  const name = "name" in node.author ? node.author.name : undefined;
  return (
    <li className={`tree-node${node.id === focus ? " focus" : ""}${node.corrects ? " correction" : ""}`}>
      <div className="tree-line">
        {node.id === focus ? (
          <strong aria-current="true">{node.title}</strong>
        ) : (
          <Link to={`/post/${node.id}`}>{node.title}</Link>
        )}{" "}
        <KindBadge kind={node.kind} />
        {node.hidden && <Badge tone="bad">hidden</Badge>}
        {node.corrects && <Badge tone="accent">corrects earlier post</Badge>}
        {corrected && <Badge tone="warn">superseded</Badge>}{" "}
        <span className="meta">
          <ParticipantLink id={node.author.id} name={name} /> · {when(node.created)}
        </span>
      </div>
      <Branches node={node} focus={focus} />
    </li>
  );
}
