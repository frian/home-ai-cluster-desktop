# Home AI Cluster Desktop

Home AI Cluster Desktop is an independent, local Chat client for [Home AI Cluster](https://github.com/frian/home-ai-cluster) (HAC). HAC handles routing and execution. The Desktop uses the accepted ordinary native Chat endpoint.

## Development

Install [uv](https://docs.astral.sh/uv/), then sync and launch:

```sh
uv sync --locked
uv run home-ai-cluster-desktop
```

HAC must already be running at its ordinary loopback endpoint. Enter a message and click **Send**. Each click sends that message as a new Chat request; displayed messages are never sent as context. Whitespace-only input does nothing.

The default client wait is 120 seconds. To choose a wait from 1 to 3600 seconds for this launch:

```sh
uv run home-ai-cluster-desktop --timeout-seconds 300
```

This first window supports ordinary Chat only. A timeout ends the Desktop wait; it does not establish whether HAC-side work continued or stopped.

Run checks with:

```sh
uv lock --check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest -q
```

Licensed under AGPL-3.0-or-later; see [LICENSE](LICENSE).
