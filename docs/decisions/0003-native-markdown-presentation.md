# 0003: Native Markdown presentation

Status: Accepted for Desktop implementation

## Decision

Desktop will use native Qt Markdown presentation for HAC response bodies. It
will use the GitHub Markdown dialect with `MarkdownNoHTML`, without an external
Markdown parser, WebView, or general-purpose rendering framework. This applies
only to HAC responses; user messages and request-status presentation remain
plain text.

The first implementation may present ordinary paragraphs, headings, emphasis,
lists, blockquotes, inline code, fenced code blocks, tables, and link text.
This decision does not claim exhaustive support for every Qt Markdown construct
or platform.

## Safety and privacy

HAC response content is untrusted presentation input. A resource-blocking
`QTextDocument` must be installed before Markdown parsing, layout measurement,
or painting. It must reject every document-driven resource request without
delegating to Qt's default loader, including HTTP(S), file URLs, relative local
paths, data URLs, and other resource types. Markdown images are outside the
first version's supported rendered content: no image resource may load.

If the blocking document observes any resource request, Desktop must present
the complete original HAC response as plain text. This whole-response fallback
uses the received string, not `toPlainText()` or `toMarkdown()`, and prevents
an unavailable-image placeholder from silently substituting inaccessible
original content. Resource-request detection must rely on the blocking
document, not regular expressions or a custom Markdown parser. It applies to
requests during parsing, layout, resizing, or painting; a late request must
not authorize loading or continued incomplete Markdown presentation. If safe
Markdown presentation cannot be established before exposure, Desktop must
conservatively use the original plain-text presentation.

`MarkdownNoHTML` is necessary but not sufficient for this boundary. Link text
may be represented visually, but links must not navigate, launch applications,
open browsers, or access local files. Mouse-only text selection remains the
interaction mode. An ordinary displayed, non-activated Markdown link is not a
document resource request and must not itself trigger fallback.

Response content remains transient visible-widget state. Desktop must not
persist prompts or responses by default. This presentation change creates no
HAC endpoint, routing, capability, runtime, adapter, timeout, stop-waiting, or
conversation-context behavior.

## Layout and fallback

Existing response UX remains: read-only selectable and copyable text, 130%
proportional line spacing, height-for-width sizing, complete vertical
visibility through the one outer conversation scrollbar, centered conversation
layout, and current message-width limits.

Markdown rendering is used only when the laid-out document fits the actual
available text width. Measurement must use the resource-blocking document,
`QTextDocument.setTextWidth()`, the real text viewport and relevant margins,
and its resulting laid-out width. The 720 px response-frame limit and
`QTextDocument.idealWidth()` alone are not sufficient criteria.

Desktop must display the complete original response as plain text when either
Markdown needs more horizontal space or the blocking document detects any
resource request. The fallback covers the whole response, uses the received
text rather than `toPlainText()` or `toMarkdown()`, and preserves text,
copying, wrapping, scrolling, and 130% spacing. It must never silently clip,
truncate, transform, or partially discard response content, and must not add
horizontal scrolling.

Desktop reevaluates presentation when effective available text width changes.
It may switch between Markdown and original-text fallback as a window narrows
or widens, without resubmitting, contacting HAC, reconstructing conversation
context, persisting content, or causing layout instability. Unchanged effective
width should not cause unnecessary presentation changes.

Markdown-mode presentation can intentionally differ from the original source:
formatting markers may disappear, soft breaks and blank lines may normalize,
and copied rendered text may differ. A separate **Copy original Markdown**
action is out of scope. The plain-text fallback, however, retains exact
original response text.

## Alternatives considered

| Alternative | Assessment |
| --- | --- |
| Continue plain-text-only presentation | Safest existing behavior, but literal Markdown reduces readability. |
| Native Markdown with silent clipping | Rejected: it can make response content inaccessible. |
| Horizontal scrolling for oversized Markdown | Rejected: it weakens the established responsive, single-scrollbar presentation. |
| Transform or wrap preformatted code | Rejected: it changes generated content and is not needed when complete fallback exists. |
| Native Markdown with complete plain-text fallback | Chosen: native Qt improves ordinary content while retaining complete original text for overflow. |
| External renderer or WebView | Rejected for this first version: adds dependencies and a broader security/rendering surface without a concrete need. |

## Verification and limitations

The implementation must verify ordinary Markdown rendering; disabled HTML and
link activation; absence of document-driven network or filesystem access;
oversized fenced-code and table detection; ordinary prose and ordinary
non-activated Markdown links without needless fallback; and exact
original-text fallback. It must also verify that HTTPS image URLs, file URLs,
relative filesystem paths, and data URLs each cause resource-triggered
whole-response fallback without loading, reading, or decoding the resource;
that requests during layout measurement, resizing, or painting remain blocked
and fall back safely; and that no inaccessible image placeholder is silently
presented. Resize stability, preserved selection, copying, spacing, and
vertical reachability, plus no HAC networking or request regression, remain
required. These tests belong to the later implementation PR. The evidence so
far is bounded Qt 6.12/Linux offscreen work, not exhaustive cross-platform or
timing validation.
