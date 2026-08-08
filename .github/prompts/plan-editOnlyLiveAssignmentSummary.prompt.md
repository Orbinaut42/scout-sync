## Plan: Edit-Only Live Assignment Summary

The assignment table will become a client-only editor aid: it appears only after entering edit mode and enabling its footer switch, updates from unsaved controls, and is always hidden in print output. The prior cache-backed route and server aggregation are removed from scope.

### Phase 1 — Edit-only shell

1. Add a static summary-table fragment beside [scout_sync/app/templates/fragments/event_table.html](scout_sync/app/templates/fragments/event_table.html).
   - Include **Scouter**, **BBL / Eurocup**, **ProA**, **Sonstige**, and **Gesamt** columns.
   - Provide stable DOM hooks and a German empty state.
   - Do not require server-provided assignment rows.

2. Update [scout_sync/app/templates/base.html](scout_sync/app/templates/base.html):
   - Place the persistent, initially hidden panel after `#content` and directly before `#appFooter`.
   - Add an accessible summary switch beside `editModeToggle`.
   - Give the switch `aria-controls` and synchronize its expanded/hidden state.

3. Restrict both controls to edit mode:
   - Hide the switch whenever `#eventEditor` is absent, using the established CSS pattern for editor-only footer controls.
   - Force-hide the panel outside edit mode even if stale DOM or checkbox state remains.
   - Reset the toggle, clear rendered rows, and hide the panel whenever edit mode ends or a new editor session begins.

4. Update [scout_sync/app/web/style.css](scout_sync/app/web/style.css):
   - Keep the panel immediately above the footer.
   - Add constrained scrolling and narrow-screen behavior.
   - Add an explicit print rule that hides the entire panel with `!important`, regardless of toggle state.

### Phase 2 — Live editor aggregation

5. Add a small locally served vanilla-JavaScript summary controller, loaded after HTMX from [scout_sync/app/templates/base.html](scout_sync/app/templates/base.html).
   - Do not introduce Node, a bundler, browser-test tooling, server aggregation, or a summary endpoint.

6. While both the footer switch and `#eventEditor` are active, calculate summary rows from the current DOM:
   - Iterate `tr[data-game-id]` within `#editEventTable`.
   - Read each row’s current league input and all scouter selects.
   - Ignore blank selections and count repeated selections separately.
   - Include all rows regardless of date.
   - Classify exact `BBL` and `Eurocup` values together, exact `ProA` separately, and every other value—including blank, case, and whitespace variants—as **Sonstige**.
   - Sort occurring names alphabetically, calculate totals, and update the existing tbody with safe text-based DOM operations.

7. Recalculate only when needed:
   - Enabling the assignment switch.
   - Typing into a league field.
   - Changing a scouter select.
   - HTMX swaps that add a new editor row or replace `#content`.
   - Clicking the existing delete button, after its row has been removed.

   Use delegated listeners and one queued refresh per animation frame or short debounce so dynamically inserted rows require no rebinding.

8. Preserve lifecycle behavior:
   - A successful save switches to read-only mode and hides/resets the table.
   - Password or validation failures update only the toast, leaving visible live values intact.
   - Leaving edit mode without saving clears the table; no cached version appears in view mode or after reload.
   - DBB-locked rows retain their fixed league, while their editable scouter selects still contribute to live totals.

### Phase 3 — Validation

9. Extend [tests/test_app.py](tests/test_app.py), using [tests/conftest.py](tests/conftest.py):
   - Replace the old assertion that statistics are absent.
   - Verify the full page has an initially hidden summary panel, an accessible editor-only switch, and a referenced/served static controller.
   - Verify read-only and editor fragments do not independently render a visible summary.
   - Keep existing route assertions; do **not** add `/list/assignments`.

10. Manually verify browser behavior because [pyproject.toml](pyproject.toml) provides pytest but no browser-JavaScript test framework:
   - The switch and table are unavailable in read-only mode.
   - Opening edit mode starts with the table hidden.
   - Selecting scouters, changing league values, duplicating a selection, adding a row, and deleting a row update counts immediately.
   - Locked DBB rows count scouter edits in their fixed category.
   - Failed saves retain live values; successful saves and leaving edit mode clear them.
   - The table works on narrow screens and never appears in print preview.

### Decisions

- The table is visible **only** in edit mode and only when enabled by its footer switch.
- It is hidden for every new editing session.
- It is excluded from all print output.
- It uses current unsaved editor values only; no cache, sync, calendar, or persistence behavior changes.
- Strict league matching and duplicate-selection counting remain unchanged.
