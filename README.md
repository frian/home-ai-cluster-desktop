# Home AI Cluster Desktop

Home AI Cluster Desktop is an early-stage, cross-platform desktop client for [Home AI Cluster](https://github.com/frian/home-ai-cluster) (HAC). It is a separate process and repository. HAC remains responsible for cluster behavior; Desktop does not embed or import HAC.

The accepted boundary is [RFC-0151](https://github.com/frian/home-ai-cluster/blob/post-1.1-development/RFC/RFC-0151-independent-desktop-thin-client.md). The first intended functional increment is a small PySide6 / Qt Widgets ordinary Chat window using HAC's accepted native Chat contract. No Chat functionality or window exists in this bootstrap.

## Development

Install [uv](https://docs.astral.sh/uv/), then run:

```sh
uv sync --locked
uv lock --check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest -q
```

The project supports Python 3.13 and 3.14. This repository does not start HAC or manage its configuration.

Licensed under AGPL-3.0-or-later; see [LICENSE](LICENSE).
