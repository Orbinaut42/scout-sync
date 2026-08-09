(() => {
  'use strict'

  const assignments = new Map()
  document.getElementById('editModeToggle').checked = false

  function setSummaryVisibility() {
    const toggle = document.getElementById('assignmentSummaryToggle')
    const summary = document.getElementById('assignmentSummary')
    
    toggle.setAttribute('aria-expanded', String(toggle.checked))
    summary.hidden = !toggle.checked
    return toggle.checked
  }

  function renderSummary() {
    const body = document.getElementById('assignmentSummaryBody')
    body.replaceChildren()
    const entries = [...assignments.entries()].sort(([first], [second]) =>
      first.localeCompare(second, 'de'))

    for (const [name, counts] of entries) {
      const row = document.createElement('tr')
      const total = counts.bbl + counts.proA + counts.other
      for (const value of [name, counts.bbl, counts.proA, counts.other, total]) {
        const cell = document.createElement('td')
        cell.textContent = String(value)
        row.append(cell)
      }
      body.append(row)
    }
  }

  function updateAssignments(forceRender = false) {
    const leagueCategory = (league) => {
        if (league === 'BBL' || league === 'Eurocup') {
        return 'bbl'
        }
        if (league === 'ProA') {
        return 'proA'
        }
        return 'other'
    }
    
    assignments.clear()

    const rows = document.querySelectorAll('#editEventTable tr[data-game-id]')

    for (const row of rows) {
      const league = row.querySelector('[data-assignment-league]')?.value || ''
      const category = leagueCategory(league)
      const scouters = row.querySelectorAll('[data-assignment-scouter]')

      for (const scouter of scouters) {
        const name = scouter.value
        if (!name) {
          continue
        }

        const counts = assignments.get(name) || {
          bbl: 0,
          proA: 0,
          other: 0}
        counts[category] += 1
        assignments.set(name, counts)
      }
    }

    if (forceRender || !document.getElementById('assignmentSummary').hidden) {
      renderSummary()
    }
  }

  document.addEventListener('change', (event) => {
    const target = event.target

    if (event.target?.id === 'assignmentSummaryToggle') {
        if (event.target.checked) {
            renderSummary()
        }
        
        setSummaryVisibility()
    } else if (target?.matches('[data-assignment-scouter]')) {
      updateAssignments()
    }
  })

  document.addEventListener('input', (event) => {
    if (event.target?.matches('[data-assignment-league]')) {
      updateAssignments()
    }
  })

  document.addEventListener('click', (event) => {
    if (event.target?.closest('.deleteButton')) {
      updateAssignments()
    }
  })

document.addEventListener('htmx:afterSwap', (event) => {
    const editor = document.getElementById('eventEditor')
    if (event.detail?.target?.id !== 'content' || !editor) {
      return
    }

    updateAssignments(true)
    setSummaryVisibility()
  })
})()
