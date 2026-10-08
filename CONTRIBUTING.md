# Contributing

Use a small dedicated branch, focused commits, and a Draft pull request for review. Run validation proportional to the change; the standard checks are in [README.md](README.md).

Desktop is a separate presentation client. HAC owns cluster behavior and exposes accepted native client contracts. Keep imports and private HAC state out of Desktop, and do not implement cluster decisions or runtime access here.

Small Desktop implementation choices need no HAC RFC. If a change needs a new HAC observation, operation, authority, or client contract, take that requirement to the [Home AI Cluster architectural process](https://github.com/frian/home-ai-cluster/blob/post-1.1-development/CONTRIBUTING.md) before implementation. Document significant lasting Desktop decisions before coding them.
