# Content CSS and JavaScript Injection Plan

Status: planned, not implemented.

Depends on `docs/plans/content-playlist-separation.md`. Injection belongs to
reusable `Content`, never to `Screen` or `ScreenContent`.

## Content fields

Add optional text fields to `Content`:

- `injected_css` — CSS stylesheet text.
- `injected_javascript_before` — JavaScript executed before page scripts.
- `injected_javascript_after` — JavaScript executed after document load.

Store empty values as blank text. Add admin help text and bounded maximum sizes
for CSS and JavaScript payloads so one content item cannot create an unbounded
configuration response or browser command. Treat these fields as trusted
administrator-controlled code; they execute in page context and are not a
sandbox.

## Configuration API

Extend each playlist item in existing screen config response with the three
injection values, serialized as `null` or text. Keep current route and existing
item fields unchanged. Include injection text in configuration version hashing;
editing shared content must refresh every screen using it.

Agent config parsing must accept missing/null injection fields for compatibility
with older managers, reject non-string values, and preserve empty values as no
injection.

## Browser/CDP design

Carry an immutable injection bundle with each playlist item and preload job.
Every target gets its bundle installed before `Page.navigate`:

1. CSS uses `Page.addStyleToEvaluateOnNewDocument`. Chromium reapplies this
   style automatically on each document navigation/reload in that target.
2. Before-phase JavaScript uses
   `Page.addScriptToEvaluateOnNewDocument`, so it executes before page scripts
   for every document.
3. After-phase JavaScript is registered by the same new-document script as a
   `load` event handler. It executes after document load and is registered again
   for each new document, covering reloads as well as agent navigation.

The existing background preload path must install injections on its new target
before navigation. Activation must not install a second copy. Direct navigation
and browser recovery use the same path, so behavior stays consistent.

Wrap injected JavaScript in an agent-owned error boundary. Execute configured
source through a generated function so syntax and runtime failures can be
identified without allowing them to escape into page navigation. Use a stable
agent prefix and content identifier in console/error records. CSS insertion is
also guarded; invalid CSS declarations may be ignored by Chromium, while style
installation errors become warnings.

Do not treat injection installation or execution failures as `BrowserError`.
Continue page loading, preload readiness, activation, playlist rotation, and
browser recovery normally.

## Failure capture/reporting

Capture JavaScript syntax/runtime failures and CSS installation failures as
structured agent warnings containing:

- content identifier or URL;
- phase (`css`, `javascript_before`, `javascript_after`);
- error text.

Enable/inspect relevant CDP runtime events while navigation is being processed
so injected errors are distinguishable from page-owned errors. Preserve a
persistent new-document error marker/console prefix for reloads that occur
inside content. Injection errors must be visible in agent logs/diagnostics but
must not mark content unhealthy or trigger navigation recovery.

No new manager health or statistics fields are required for this feature.
Future management/statistics fields remain on `ScreenContent` as planned.

## Admin

Add injection fields to `ContentAdmin` with multiline, monospace-friendly
controls and clear phase descriptions. Keep fields absent from
`ScreenContentInline`; a shared content item has one injection definition for
all screens.

Document that:

- CSS is useful for presentation-only adjustments;
- before JavaScript runs before page-owned scripts;
- after JavaScript runs after document load;
- code runs with page privileges;
- failures are logged and do not stop kiosk playback.

## Tests

Add Django tests for:

- optional injection fields on screen-independent content;
- API serialization of all phases and null/empty values;
- configuration version changes when injection changes;
- shared content changes reflected on every linked screen;
- admin form/help text and payload size validation.

Add agent tests for:

- parsing missing, null, empty, and valid injection values;
- rejecting malformed injection types and oversized values;
- CDP installation order before navigation;
- CSS/before/after hooks installed for every preload target;
- reload reapplication through `Page.add*ToEvaluateOnNewDocument`;
- CSS/CDP installation errors logged without navigation failure;
- JavaScript syntax/runtime errors captured without agent crash or browser
  recovery;
- ordinary page navigation errors still follow existing recovery behavior.

Run Django and agent tests, migration checks, Ruff, Pyright, and lens
 diagnostics. No board deployment during this change.
