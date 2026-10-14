# Home AI Cluster Desktop

Home AI Cluster Desktop is an independent, local Chat client for [Home AI Cluster](https://github.com/frian/home-ai-cluster) (HAC). HAC handles routing and execution. The Desktop uses the accepted ordinary native Chat endpoint.

## Development

Install [uv](https://docs.astral.sh/uv/), then sync and launch:

```sh
uv sync --locked
uv run home-ai-cluster-desktop
```

HAC must already be running at its ordinary loopback endpoint. Enter a message and click **Send**. Chat is an ephemeral conversation owned only by the running Desktop window: each later request includes the successful earlier user/assistant exchanges from that window. Failed, stopped, timed-out, and invalid turns are not included in later context. Whitespace-only input does nothing.

The window keeps at most 65,536 UTF-8 bytes of candidate message content; requests beyond that local bound are not sent. Choose **New conversation** to clear the visible transcript and ephemeral context while preserving any unsent input. It starts fresh without saving history.

The default client wait is 120 seconds. To choose a wait from 1 to 3600 seconds for this launch:

```sh
uv run home-ai-cluster-desktop --timeout-seconds 300
```

The window also presents a snapshot of HAC-owned active routable capabilities. It reads this once at startup and again only when you choose **Refresh**. The snapshot is informational, not health, readiness, or monitoring. A timeout or **Stop waiting** ends the current Desktop Chat wait; neither establishes whether HAC-side work continued or stopped. A later Send is a new independent request.

Run checks with:

```sh
uv lock --check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest -q
```

Licensed under AGPL-3.0-or-later; see [LICENSE](LICENSE).
