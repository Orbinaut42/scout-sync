## Plan: HTMX and Bootstrap Core Editor

Migrate the current jQuery UI to server-rendered Jinja fragments, HTMX, and locally served Bootstrap CSS. Preserve Flask, cache persistence, sync behavior, and the current password-per-submit model—without adding Node, a database, sessions, or a client-side state framework.

**Confirmed scope**

- Include: read-only event list, editor, manual event add/remove, scouter assignment, locked DBB events, password feedback, view refresh on browser focus, responsive layout, print output, and cache-save/sync enqueue.
- Defer: statistics table and toggle, automatic scroll positioning, session/CSRF/rate-limit redesign, calendar-sync progress UI, and changes to the `Event`/sync domain model.

### Phase 1 — Safe application and test foundations ✅ Completed

1. ✅ Refactor scheduler initialization in [scout_sync/app/app.py](scout_sync/app/app.py) and [scout_sync/app/__main__.py](scout_sync/app/__main__.py) so importing the Flask application does not start a background scheduler.
   - Keep `app_startup()` and the [Procfile](Procfile) factory contract intact.
   - Initialize the scheduler once at startup and enqueue cache syncs through the initialized scheduler.
   - This prevents test imports from starting threads or reaching Google/DBB services.

2. ✅ Add `pytest` only as a development dependency in [pyproject.toml](pyproject.toml), with a lightweight developer installation entry point and pytest discovery configuration.
   - Do not add test dependencies to runtime [requirements.txt](requirements.txt).

3. ✅ Add locally hosted, version-pinned HTMX JavaScript and Bootstrap CSS below the existing static directory.
   - Record source version and license information.
   - Use Bootstrap CSS only; do not introduce Bootstrap JavaScript, Bootstrap Icons, npm, or a bundler.

Phase 1 validation completed with Python compilation, TOML/dependency checks, whitespace checks, and editor diagnostics. The vendored HTMX and Bootstrap assets were also recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Phase 2 — Server-rendered template structure

4. Separate Jinja templates from static files.
   - Update the Flask template directory in [scout_sync/app/app.py](scout_sync/app/app.py).
   - Keep [scout_sync/app/web](scout_sync/app/web) as the static directory and preserve its `/list` URL prefix.
   - Move the current shell from [scout_sync/app/web/list.html](scout_sync/app/web/list.html) into a new server-template directory, preventing partial templates from being served as static files.

5. Split the UI into reusable server-rendered fragments:
   - Page shell.
   - Read-only event table.
   - Editable event form/table.
   - Single editable event row.
   - Inline success, validation, password, empty-cache, and error messages.

6. Add rendering helpers in [scout_sync/app/app.py](scout_sync/app/app.py) to provide:
   - Sorted cache events.
   - Configured scouter names.
   - Configured timezone/current time.
   - Optional feedback messages.
   - German server-side date/time formatting using timezone-aware `arrow` values.

### Phase 3 — HTMX core dashboard and editor

7. Replace the jQuery page lifecycle with Bootstrap markup and HTMX attributes.
   - Use Bootstrap containers, responsive tables, forms, buttons, alerts, and visibility utilities.
   - Replace image-only buttons with accessible labelled controls.
   - Remove references to jQuery and the legacy client script once equivalent behavior is covered.

8. Add parallel HTML fragment routes while preserving legacy JSON routes:
   - `GET /list/hx/events` returns the read-only table fragment.
   - `GET /list/hx/edit` returns the populated editor form.
   - A small row-fragment route returns a new manual-event row with a collision-resistant server-generated ID.
   - `POST /list/hx/edit` handles normal HTML form submission.
   - Preserve `GET /list/events` and JSON `POST /list/edit` unchanged for compatibility.

9. Render the initial event list on the server and use HTMX to refresh it when the browser regains focus.
   - Attach focus refresh only to the read-only view.
   - Do not refresh while editing, so unsaved changes cannot be discarded.

10. Preserve current editor rules from [scout_sync/app/web/list.js](scout_sync/app/web/list.js):
    - Manually created events remain fully editable and removable.
    - DBB-backed events keep date, time, location, league, and opponent locked.
    - DBB-backed events still allow scouter assignment.
    - Render at least three scouter selects, plus additional selects for existing assignments.
    - Removing a row only changes the unsaved form; no individual row action writes cache data or calendar data.

11. Use stable per-row form keys rather than positional client arrays.
    - Group repeated scouter values safely during form parsing.
    - Generate new manual event IDs on the server.
    - Parse date/time values using the configured timezone, never browser-side `Date.parse`.

12. Protect sync correlation data at the server boundary.
    - Re-load current cache events before saving.
    - Treat `schedule_info` and schedule-owned fields as authoritative cache data, not client-controlled hidden fields.
    - Rehydrate DBB-backed events and preserve them even if a crafted request omits a locked row.
    - Validate duplicate IDs, date/time input, and submitted scouter names before calling `Event.from_json()` and `WebCacheHandler.store_events()` from [scout_sync/sync/sync.py](scout_sync/sync/sync.py).

13. Handle HTMX feedback without losing the form:
    - On success, store events, enqueue the existing `sync(source='cache')`, and replace the editor with the view plus a Bootstrap success alert.
    - On wrong password or invalid input, return a retargeted inline Bootstrap alert while keeping the submitted editor DOM intact.
    - Keep the legacy JSON route’s existing `400`/`401` behavior unchanged.
    - Keep `escape_json()` and `unescape_json()` only for the legacy JSON API; rely on Jinja autoescaping for HTML fragments.

### Phase 4 — Styling, cleanup, and documentation

14. Replace the legacy custom styling in [scout_sync/app/web/style.css](scout_sync/app/web/style.css) with small Bootstrap supplements:
    - Column constraints and compact table layout.
    - Past-event and locked-field styling.
    - Narrow-screen behavior.
    - Sticky editor controls where useful.
    - Print rules that hide editor controls and retain a readable event table.

15. Remove unused assets only after confirming no template or stylesheet still references them.
    - Remove the jQuery script and [scout_sync/app/web/list.js](scout_sync/app/web/list.js).
    - Remove obsolete add/delete image assets if replaced by text-labelled Bootstrap buttons.
    - Keep the favicon and any asset still used.

16. Update [AGENTS.md](AGENTS.md) after the migration to document:
    - Jinja + HTMX + Bootstrap architecture.
    - Locally served frontend assets and no-build policy.
    - New fragment routes.
    - Pytest command.
    - Legacy JSON compatibility and `schedule_info` preservation requirements.

### Phase 5 — Verification

1. Add isolated pytest fixtures using:
   - A temporary cache file.
   - Test configuration values.
   - A fake scheduler/enqueue function.
   - No Google Calendar, DBB HTTP, or real scheduler startup.

2. Test the full page and fragments:
   - Sorted German date display.
   - Escaped user content.
   - Scouter options.
   - DBB row locking.
   - New manual row generation.
   - No statistics UI in this release.

3. Test form submission:
   - Correct password writes only the temporary cache.
   - `id` and `schedule_info` remain preserved.
   - Schedule-managed fields and rows cannot be removed or altered through submitted form data.
   - Exactly one cache-sync job is queued.
   - Wrong passwords and malformed rows show inline feedback without replacing unsaved fields.

4. Regression-test legacy endpoints:
   - `GET /list/events` continues to return the escaped event JSON schema.
   - JSON `POST /list/edit` continues to return expected success, `400`, and `401` responses.

5. Run:
   - `python -m pytest`
   - `python -m compileall scout_sync`
   - `python -m flake8`

6. Manually exercise `/list` with cached events and simulated sync enabled:
   - Desktop and mobile layout.
   - View → edit → cancel.
   - Add/remove a manual event.
   - Change scouters.
   - Invalid and valid password behavior.
   - Refresh-on-focus in view mode.
   - Printed read-only output.

**Key boundaries**

- [scout_sync/sync/sync.py](scout_sync/sync/sync.py) remains the authoritative event conversion, cache, and calendar-diff layer.
- The cache file location and existing configuration keys remain unchanged.
- No authentication redesign is included; the current password configuration remains in use.
- Statistics and auto-scroll behavior are intentionally deferred to a later increment.
