# 0001: Active capability presentation

Status: Accepted for Desktop implementation

Desktop may present HAC's RFC-0152 active caller-routable capability projection. Its only source is `GET http://127.0.0.1:25042/diagnostics/caller-routable-capabilities`. Desktop reads one snapshot when the window starts and reads another only when the user chooses **Refresh**. There is no periodic polling or automatic retry.

The displayed snapshot is presentation state only and is never persisted. A successful refresh replaces it, including when the returned set is empty. A failed refresh replaces it with **Capabilities unavailable**; an old snapshot must not remain presented as current truth. Failure says nothing about HAC connectivity, health, readiness, or whether a future request can execute.

Capability names are HAC-owned data. Desktop does not reproduce capability membership or routing rules, and the projection is informational rather than a capability selector. This decision adds no monitoring, dashboard, health, topology, node, model, runtime, background subscription, cache, or discovery UI.

A capability observation has a Desktop-local fixed 5-second wait, independent of the Chat wait. Expiry ends this observation and makes Refresh available; it does not establish any HAC-side state.
