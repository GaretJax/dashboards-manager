# Image and Video Content Plan

Status: implemented; production media rollout validation pending.

Depends on `docs/plans/content-playlist-separation.md` and the existing HTML
content delivery path. Playlist items continue to expose one browser URL; the
agent does not need media-specific behavior.

## Content model

Represent the three content sources as three mutually exclusive fields:

- `url = URLField` — remote page, existing behavior;
- `html = TextField` — full UTF-8 HTML document stored in the database,
  populated through an admin file widget;
- `media = FileField` — uploaded image or video.

`html` intentionally stores the complete document rather than a storage
path. A custom form/widget reads the uploaded file as UTF-8 and assigns its
contents to `html`; editing should replace the stored document atomically.
Apply a maximum document size appropriate for database storage and reject
invalid UTF-8. The migration should read each existing `html_file` object,
store its decoded contents in `html`, and leave old storage objects for a
separate post-migration cleanup after verification.

Use a database constraint and `clean()` validation requiring exactly one of
`url`, `html`, or `media`. Infer image versus video from the validated
`python-magic` MIME/extension; no user-editable media type field is required.
Use `models.TextChoices` for the internal media category/validation result if a
stable category is needed by forms or templates.

Limit media to formats with reliable Chromium support on kiosk boards:

- images: JPEG (`.jpg`, `.jpeg`), PNG (`.png`), GIF (`.gif`), WebP (`.webp`),
  AVIF (`.avif`), and SVG (`.svg`);
- video: MP4 (`.mp4`, H.264/AAC expected) and WebM (`.webm`, VP8/VP9/Opus or
  Vorbis expected).

Reject TIFF, BMP, MOV, AVI, MKV, Ogg, and arbitrary extensions unless
board-specific Chromium testing proves a format reliable. Extension checks
must be paired with content inspection using `python-magic`, not the
client-provided MIME header. Read a bounded prefix, reset the upload stream,
and require the detected MIME to match the extension allowlist (`image/avif`
and `image/svg+xml` for the new formats). SVG must be rendered only as an
`<img>` source, never as the HTML page itself; do not allow SVG uploads to
become navigable HTML. If future features need inline SVG, add sanitization
first. Codec validation can be documented as an upload requirement or added
later with `ffprobe`.

Add `python-magic` to Python dependencies. Install matching `libmagic1` in
Django development, test, and production images. Agent hosts do not need the
library because upload inspection runs in Django.

Keep shared-content fields (`label`, preload settings, injections, timestamps)
unchanged. Injection fields should be disabled or clearly documented for
media pages unless media-page injection is deliberately supported.

Use a migration that replaces `html_file` with the HTML text field, adds the
media field, backfills existing HTML contents, updates constraints, and leaves
media object names unchanged. Update model stringification to use label, URL,
HTML title/label, or media filename.

## Admin and validation

Update `ContentAdmin` and any upload form to show:

- content type;
- HTML upload widget that reads the selected file into `html`;
- media upload field;
- URL only for URL content;
- HTML widget only for HTML content;
- media widget only for image/video content.

Use a custom `Content` form for conditional fields and friendly validation.
Reject a type/file mismatch, empty URL/HTML/media combinations, unsupported
extensions, and files whose `python-magic` MIME does not match the allowlist.
Do not trust the browser's declared MIME type. Keep upload fields out of
`ScreenContentInline`; content remains reusable.

Add admin help text explaining that uploaded images and videos are rendered by
Kiosk Manager, not served as arbitrary HTML.

## Configuration API and URLs

Keep `content_url()` returning the existing endpoint for every uploaded type:

```text
/screens/<screen-token>/contents/<content-id>/
```

The screen configuration API continues returning that URL. It must detect
`url`, `html`, and `media` instead of checking only `html_file`. Include the
source fields and media-relevant values in configuration version hashing so
replacing a file or changing a source refreshes the agent.

Keep endpoint authorization unchanged: the screen must be enabled and the
content must be linked to that screen.

## Media delivery views

Split the existing content view into two responsibilities:

1. **HTML content:** preserve current behavior and security headers, returning
   the database-stored HTML directly from the existing endpoint.
2. **Image/video content:** render a new Django media page from that same
   endpoint.

Media page requirements:

- black background;
- viewport-sized flex/grid container centered both directions;
- no scrollbars;
- image/video uses intrinsic dimensions with `width: auto`, `height: auto`,
  `max-width: 100%`, and `max-height: 100%` so it is never upscaled and keeps
  its aspect ratio;
- use `object-fit: contain` as a safety measure for video sizing;
- image has useful alt text from label or filename;
- video uses `autoplay`, `muted`, `playsinline`, `preload="auto"`, no
  `controls`, and no audio track exposure where the browser permits it;
- do not add `loop` unless playlist requirements later call for it; playlist
  duration remains authoritative.

For image and video pages, use the storage backend's generated media URL
(`content.media.url`) directly. Production S3 is responsible for serving the
bytes and supporting HTTP Range requests; Django must not proxy media bytes.
The outer playlist URL remains the existing content endpoint, while the page's
`img`/`video` element points at the S3 URL.

Ensure uploaded media receives the correct object `Content-Type` metadata and
is served `inline` with `Accept-Ranges` support. The configured S3 URL must be
publicly readable or signed for the page's lifetime. Verify that the S3
endpoint supports browser video range requests and that any required CORS
policy is configured. Do not expose arbitrary storage paths; only render the
storage URL for an authorized, linked content object.

Build the media CSP from the generated media URL origin, at minimum
`default-src 'none'`, inline styles, `img-src <media-origin>`, and
`media-src <media-origin>`. If storage uses a custom domain, use that origin;
do not copy signed URL query parameters into CSP. Avoid inline script if muted
autoplay attributes are sufficient; otherwise add only the narrowly scoped
playback script required by browser autoplay behavior.

## Templates and styling

Add a dedicated `templates/kiosks/content_media.html` template rather than
putting media markup in `screen.html`. Keep database-stored HTML served
byte-for-byte as before. Add a stable class/data attribute to media elements
for browser smoke tests and future injected CSS.

## Agent impact

No new media logic is required in the agent. It already navigates playlist URLs
and waits for page load. Verify that preload, activation, screenshot capture,
CSS injection, and configuration version changes work with the generated media
page. If video pages report `load` before the first frame is ready, use the
existing preload delay/timeout settings rather than adding media-specific
agent code.

## Tests

Add Django tests for:

- type choices, migration backfill into full HTML text, URL/HTML/media
  constraints, UTF-8/size validation, and `python-magic` MIME validation;
- configuration URLs for HTML, image, and video uploads;
- configuration version changes when source or uploaded file changes;
- HTML endpoint backward compatibility and existing CSP/security headers;
- image page markup, black centered layout, no-upscale sizing, and JPEG,
  PNG, WebP, AVIF, and SVG MIME handling;
- video page markup, autoplay/muted/playsinline/no-controls attributes;
- generated S3 media URLs, MIME metadata, missing files, and CSP media
  origins;
- disabled screens and unlinked content returning 404;
- admin conditional fields and validation;
- rendered installer does not include manager-only `libmagic1`.

Add agent tests confirming media URLs are treated like ordinary playlist URLs
and that preloading/activation passes through without special cases.

Run migrations/checks, Django tests, agent tests, Ruff, Pyright, and endpoint
smoke tests. No board or production rollout until media delivery and range
handling are verified.

## Rollout sequence

1. Add migration, model/form/admin changes, and compatibility handling.
2. Implement media page and direct S3 asset URL handling.
3. Update API/version hashing and tests.
4. Build image with existing storage configuration and run full validation.
5. Create one test screen with image and video content using local storage.
6. Verify S3-backed uploads, object MIME metadata, S3 range requests,
   Chromium autoplay/mute behavior, and playlist transitions.
7. Deploy only after explicit approval.
