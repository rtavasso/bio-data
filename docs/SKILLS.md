# Research workflow skills

The repository ships six focused skills in `.agents/skills/`. Codex discovers repository skills from that directory; each skill also supports explicit invocation. See the [official skill documentation](https://learn.chatgpt.com/docs/build-skills).

| Skill | Use it for |
| --- | --- |
| [`bio-research`](../.agents/skills/bio-research/SKILL.md) | A biological question, source-backed analysis, a notebook and reusable outputs |
| [`bio-mechanism-exploration`](../.agents/skills/bio-mechanism-exploration/SKILL.md) | Recursive upstream investigation, competing explanations, evolving networks and data blind spots |
| [`bio-hypothesis-discovery`](../.agents/skills/bio-hypothesis-discovery/SKILL.md) | Candidate selection, falsifiable predictions, independent tests and scoped novelty audits |
| [`bio-data-discovery`](../.agents/skills/bio-data-discovery/SKILL.md) | Selecting useful measurements, inspecting exact files and recording access gaps |
| [`bio-artifact-reuse`](../.agents/skills/bio-artifact-reuse/SKILL.md) | Assessing an existing derivation or registering and reusing a new representation |
| [`bio-evaluation-review`](../.agents/skills/bio-evaluation-review/SKILL.md) | Reviewing an agent's transcript and outputs to propose concrete improvements |

For example: “Use $bio-research to investigate whether this PMP22 result could be explained by cell composition.” Or: “Use $bio-evaluation-review to diagnose this recorded evaluation run.” A fresh session can also select a relevant skill implicitly. No personal configuration or plugin installation is required for this checkout.

The skills support ordinary research decisions; they do not impose a scientific acceptance state machine. They use the current CLI, preserve source/derivation semantics, and point to detailed documentation only when needed. Use `bio` when it is already on PATH, or `uv run bio` in a development checkout. Honor the supplied `BIO_WORKSPACE`.

Sustained investigations use the mechanism skill's [investigation queue](../.agents/skills/bio-mechanism-exploration/references/investigations.md) to carry unresolved questions between sessions. The research and discovery skills connect those priorities to actual measurement processing, broader exploratory analysis, preserved primary sources and reproducible outputs. Evaluation review checks what was newly executed and whether consequential feasible work remained at stopping.

See [the workflow guide](WORKFLOW.md) to start research and [agent evaluation](EVALUATION.md) to test skill changes on repeatable questions. Evaluation manifests pin the actual skill bytes so later edits can be compared to the tested version.
