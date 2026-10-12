# 0002: Explicit Chat wait stop

Status: Accepted for Desktop implementation

Desktop may let a user explicitly stop awaiting its one outstanding Chat response. This is a Desktop-client operation: it ends the current client wait, restores the ability to submit a new independent Chat request, and leaves the submitted message visible.

Stopping the wait does not establish that HAC execution stopped, failed, completed, or was cancelled. HAC may continue processing the original request. A response or error delivered later for the abandoned wait is ignored and must not change the visible conversation or newer request state.

Stopping does not retry, resend, queue, or persist anything. The invocation-local Chat timeout remains unchanged. This decision adds no HAC endpoint, request field, cancellation protocol, cancellation authority, request tracking, or conversation history.
