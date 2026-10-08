# Agent guidance

Read [Home AI Cluster RFC-0151](https://github.com/frian/home-ai-cluster/blob/post-1.1-development/RFC/RFC-0151-independent-desktop-thin-client.md) before implementing Desktop behavior. Architecture precedes implementation: agents implement accepted decisions; they do not own architectural decisions.

Desktop is an independent client, not another orchestrator. Never import `home_ai_cluster`, inspect HAC private state, contact a model runtime directly, or reproduce HAC routing, capability, topology, runtime, adapter, fallback, or retained Configuration semantics. Use only accepted native HAC client contracts. If a needed HAC function lacks one, return the requirement to the `home-ai-cluster` architectural process before implementation.

Keep changes small and concrete. Use dedicated branches, focused commits, and Draft pull requests. Avoid abstractions before a concrete need. Desktop-only choices can be made here when they preserve HAC contracts and authority; document significant durable Desktop architecture before implementing it. Preserve local-first and privacy-first behavior without default prompt or response retention.
