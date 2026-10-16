# Agent guidance

Read [Home AI Cluster RFC-0151](https://github.com/frian/home-ai-cluster/blob/post-1.1-development/RFC/RFC-0151-independent-desktop-thin-client.md) before implementing Desktop behavior. Architecture precedes implementation: agents implement accepted decisions; they do not own architectural decisions.

Desktop is an independent client, not another orchestrator. Never import `home_ai_cluster`, inspect HAC private state, contact a model runtime directly, or reproduce HAC routing, capability, topology, runtime, adapter, fallback, or retained Configuration semantics. Use only accepted native HAC client contracts. If a needed HAC function lacks one, return the requirement to the `home-ai-cluster` architectural process before implementation.

Keep changes small and concrete. Use dedicated branches, focused commits, and Draft pull requests. Avoid abstractions before a concrete need. Desktop-only choices can be made here when they preserve HAC contracts and authority; document significant durable Desktop architecture before implementing it. Preserve local-first and privacy-first behavior without default prompt or response retention.

## Shared project coordination

The canonical coordination repository is `frian/home-ai-cluster-project`.
For substantial non-BLIND work, consult its current `PROJECT-STATUS.md` when
accessible, identify the relevant workstream, and verify Git references before
acting. Coordination records are not architectural authority and do not
supersede accepted RFCs or this repository's instructions.

After a significant milestone (for example, a Draft PR, merge, accepted RFC,
release, verified blocker, or completed review), briefly propose an update to
the operator when it would change a workstream or merit a durable log entry.
Do not propose updates for trivial intermediate steps. Do not write to the
coordination repository without explicit operator authorization.

If authorized, follow the coordination repository's current `README.md`:
refresh the remote files, preserve concurrent changes, update status only when
needed, and record meaningful milestones. Routine updates may be committed
directly to its `main`; convention changes require a dedicated branch and
Draft PR. Do not modify any other repository without explicit authorization.
