# Scout Sync agent instructions

## Application outline

- The application has two main tasks: keeping game events in a calendar up to date with a online database ("DBB schedule") and allowing users ("scouters") to assign themselves or others to these games.
- The calendar is synchronized periodically by the server with the online database.
- The result of the calls to the online database API may be unreliable, so careful validation is neccessary to avoid incorrect deletion of events.
- The UI displays the list of games and also allows editing and manually adding games
- For games from the DBB schedule only assigning scouters is allowed, for manually created games all properties can be edited.
- The edits from the UI are synced back to the calendar, the scouters are added as attendants in the calendar events.

## Project shape

- The main synchronization orchestration and `Event` conversion model are in [scout_sync/sync/sync.py](scout_sync/sync/sync.py).
- Google authentication and API wrappers are in [scout_sync/sync/google_api.py](scout_sync/sync/google_api.py).
- Flask routes and the background scheduler are in [scout_sync/app/app.py](scout_sync/app/app.py); server-rendered browser templates are under [scout_sync/app/templates](scout_sync/app/templates), with local static assets under [scout_sync/app/web](scout_sync/app/web).
- The frontend uses Jinja fragments, HTMX, and locally served Bootstrap CSS. There is no Node, bundler, or frontend build step.
- Configuration loading is centralized in [scout_sync/config/__init__.py](scout_sync/config/__init__.py).


## Run and validate

- Install dependencies from [requirements.txt](requirements.txt), or use the Poetry metadata in [pyproject.toml](pyproject.toml).
- Run the development app with `python -m scout_sync.app`.
- Run a sync from the live DBB schedule with `python -m scout_sync.sync --from schedule`.
- Run a sync from the cached JSON events with `python -m scout_sync.sync --from cache`.
- Refresh OAuth credentials with `python -m scout_sync.sync --refresh-credentials`.
- Production uses the command in [Procfile](Procfile).
- Run `python -m pytest` for the configured test suite. There is no formatter or CI configuration; for changes, at minimum compile-check modified Python files and manually exercise the affected CLI or Flask route when credentials/configuration permit.
- Use flake8 for linting.

## Configuration and safety

- Do not commit, print, or expose credentials. Treat [scout_sync/config/scout_sync.cfg](scout_sync/config/scout_sync.cfg), the local override, and [scout_sync/sync/secrets.json](scout_sync/sync/secrets.json) as sensitive; use the template/local configuration and environment variables for development.
- Configuration is loaded from the package config and supplemented by environment variables including `EMAILS`, `SUBMIT_PW`, `OAUTH_INFO`, and `SERVICE_ACCOUNT_INFO`.
- Runtime paths such as the log and web-cache files come from the `[COMMON]` configuration section; do not hard-code them.
- The sync flow has external side effects: Google Calendar writes, DBB HTTP requests, and cache writes. Prefer `simulate` mode or cache input before testing behavior that mutates remote data.
- Preserve event identifiers and `schedule_info`; they are used to correlate DBB records with Google Calendar records and to decide whether events are added, updated, or deleted.

## Implementation conventions

- Keep changes focused and preserve the existing public entry points and configuration keys.
- Use the existing module-level logging style and explicit UTF-8 for JSON/file I/O.
- Preserve timezone-aware `arrow` values and the configured timezone when creating or parsing events.
- When changing event fields or serialization, review all `Event.from_*` and `Event.as_*` conversions plus calendar diffing in `sync()`.
- For web changes, keep the Jinja + HTMX table/edit flow and Bootstrap markup. Verify `GET /list/hx/events`, `GET /list/hx/edit`, `GET /list/hx/edit/row`, and `POST /list/hx/edit` behavior, including validation and password feedback. The old `/list/events` and `/list/edit` JSON browser endpoints are removed.
- Avoid broad refactors unless requested; this code integrates with remote APIs and relies on configuration-driven behavior.
- When adding or updating docstrings, only describe what the function is currently doing, not why it was changed.
- Avoid creating helper functions that only wrap a few lines of code, if that helper is only called in one place. If helper fuctions are needed, implement them in the most local context possible.
- Read configuration values directly from the shared `config` object; do not add helper functions that only return config values. A convenient config value object may be introduced later in [scout_sync/config/__init__.py](scout_sync/config/__init__.py).
