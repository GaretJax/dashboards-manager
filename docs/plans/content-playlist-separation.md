# Content / Screen Playlist Separation Plan

Status: planned, not implemented.

## Goal

Keep `Screen` as display/device configuration. Extract reusable display material
into screen-independent `Content`. Represent each screen playlist as a through
model so one `Content` can be assigned to multiple screens.

## Model shape

### `Content`

New model, with no foreign key to `Screen`:

- `url` or uploaded `html_file` (exactly one; retain current XOR validation and
  database constraint).
- `preload_delay_seconds`.
- `preload_timeout_seconds`.
- `created_at`, `updated_at`.

Move effective preload settings onto `Content`. Existing screen-level defaults
and page-level overrides become one materialized content value during data
migration. Then remove preload fields from `Screen`; a reusable content item
cannot inherit settings from one particular screen.

Use a new `contents/` upload directory for new files, while preserving existing
stored file names during migration so current media files are not moved or
lost.

### `ScreenContent`

New explicit through model for playlist membership:

- `screen` foreign key.
- `content` foreign key.
- `order`.
- `duration_seconds` (existing API name; admin label remains “time on page”).
- `created_at`, `updated_at` for membership lifecycle tracking.

Add `Screen.contents = ManyToManyField(Content, through=ScreenContent)`.

Keep unique `(screen, order)`. Do **not** make `(screen, content)` unique:
existing playlists can contain same source more than once, and future playlist
management may need that. Management-specific fields and playback statistics
will be added to `ScreenContent` later; do not add placeholder stats columns
now.

## Migration

Add a migration that:

1. Creates `Content` and `ScreenContent`.
2. Adds `Screen.contents` through relation.
3. Copies each existing `Page` row into one `Content` plus one `ScreenContent`:
   - URL or HTML storage name copied unchanged.
   - Content preload delay receives page override when present, otherwise the
     old screen preload delay.
   - Content timeout receives page override when present, otherwise the old
     screen preload timeout.
   - Playlist order and time-on-page are copied unchanged.
4. Preserves one content per old page row; no implicit URL deduplication. This
   preserves behavior even when old screens used same URL with different
   preload settings. Reuse can be configured explicitly afterward.
5. Removes old `Page` and obsolete screen/page preload columns after data copy.
6. Adds content XOR and playlist order constraints.

Migration tests must verify URL pages, uploaded files, effective inherited
preload values, overrides, duplicate source rows, order, and duration.

## Services and API

Update configuration generation to read ordered `ScreenContent` rows with
`select_related("content")`. Keep agent response contract stable:

- `items[].url`
- `items[].duration_seconds`
- `items[].order`
- `items[].preload_delay_seconds`
- `items[].preload_timeout_seconds`

Compute item URL from `Content`; uploaded content URL should use a content
identifier and remain scoped to the requesting screen. Existing API route
`/api/screens/<public-token>/config` stays unchanged. Include content changes
in configuration version hashing, including changes to shared content.

Rename internal service concepts from page to content/playlist entry without
changing agent behavior. No agent implementation changes should be needed.

## Uploaded content delivery

Replace page lookup with a `ScreenContent` membership check joined to
`Content`. A content file is served only when that content is currently linked
to the requested enabled screen. External URLs remain returned directly.

Use a content-oriented route for new generated URLs:

`/screens/<public-token>/contents/<content-id>/`

Keep a compatibility decision explicit before implementation. Preferred option
is a short-lived alias for old `/pages/<id>/` URLs only if old API responses
could have been bookmarked; otherwise remove the old route with the model.

## Admin

- Add `ContentAdmin` for reusable URL/upload and content preload settings.
- Replace `PageInline` with `ScreenContentInline` on `ScreenAdmin`.
- Inline fields: content, order, time on page, membership timestamps.
- Remove per-page preload fields from the screen playlist inline.
- Keep screen schedule/device fields on `ScreenAdmin`.
- Add content search/listing independent of screens.

Update labels, help text, README, tests, and any references from “page” to
“content” where they describe the domain model. Keep browser protocol uses of
`Page.*` unchanged.

## Tests and verification

Add/update tests for:

- Content URL/HTML XOR and preload validation without a screen.
- One content linked to multiple screens.
- Same content linked multiple times to one screen.
- Per-screen order uniqueness.
- Configuration ordering and unchanged agent payload.
- Shared content edit changing linked screen configuration versions.
- Uploaded content access only through valid screen membership.
- Admin content CRUD and playlist inline behavior.
- Data migration preservation and rollback limitations.

Run migrations, Django tests, Ruff, Pyright, system checks, and lens
 diagnostics. No board deployment during this change.

## Decisions

1. Compatibility may break. Remove old `/pages/<id>/` delivery route; generated
   URLs use `/contents/<content-id>/`.
2. Remove screen-level preload defaults. Migration materializes each old page's
   effective preload values into reusable `Content`.
