(() => {
  'use strict'

  const fields = ['date', 'time', 'location', 'league', 'opponent', 'scouters']
  const confirmationThreshold = 10
  const scalarFields = fields.filter((field) => field !== 'scouters')
  const pending = new Map()
  const originalDataAttributes = {
    date: 'originalDate',
    time: 'originalTime',
    location: 'originalLocation',
    league: 'originalLeague',
    opponent: 'originalOpponent'}

  function rowFor(target) {
    if (!(target instanceof Element)) {
      return null
    }

    return target.closest('tr[data-game-id]')
  }

  function controlsFor(row, field) {
    return [...row.querySelectorAll(
      `[data-event-field="${field}"]`)]
  }

  function normalizeScalar(field, value) {
    const normalized = value || ''
    return field === 'time' && normalized === ''
      ? '00:00'
      : normalized
  }

  function normalizeScouters(values) {
    return values
      .filter((value) => value !== '')
      .sort((first, second) => first.localeCompare(second, 'de'))
  }

  function originalValue(row, field) {
    if (field === 'scouters') {
      try {
        const values = JSON.parse(row.dataset.originalScouters || '[]')
        return normalizeScouters(Array.isArray(values) ? values : [])
      } catch (_error) {
        return []
      }
    }

    return normalizeScalar(
      field,
      row.dataset[originalDataAttributes[field]] || '')
  }

  function currentValue(row, field) {
    const controls = controlsFor(row, field)
    if (field === 'scouters') {
      return normalizeScouters(controls.map((control) => control.value))
    }

    return normalizeScalar(field, controls[0]?.value || '')
  }

  function valuesEqual(field, first, second) {
    if (field === 'scouters') {
      return JSON.stringify(first) === JSON.stringify(second)
    }

    return first === second
  }

  function setFieldDirty(row, field, dirty) {
    for (const control of controlsFor(row, field)) {
      control.dataset.dirtyField = String(dirty)
    }
  }

  function setRowDirty(row, dirty) {
    row.dataset.dirty = String(dirty)
    row.classList.toggle('row-dirty', dirty)
  }

  function updateSubmitState() {
    const submit = document.getElementById('submitEvents')
    if (submit) {
      submit.disabled = pending.size === 0
    }
  }

  function rowHasValue(row) {
    for (const field of scalarFields) {
      const control = controlsFor(row, field)[0]
      if (control?.value) {
        return true
      }
    }

    return currentValue(row, 'scouters').length > 0
  }

  function reconcileRow(row) {
    const eventId = row.dataset.gameId
    if (!eventId) {
      return
    }

    if (row.dataset.newEvent === 'true') {
      if (rowHasValue(row)) {
        pending.set(eventId, {operation: 'create', fields: new Set(fields)})
        for (const field of fields) {
          setFieldDirty(row, field, true)
        }
        setRowDirty(row, true)
      } else {
        pending.delete(eventId)
        for (const field of fields) {
          setFieldDirty(row, field, false)
        }
        setRowDirty(row, false)
      }
      updateSubmitState()
      return
    }

    const changedFields = new Set()
    for (const field of fields) {
      const dirty = !valuesEqual(
        field,
        currentValue(row, field),
        originalValue(row, field))
      setFieldDirty(row, field, dirty)
      if (dirty) {
        changedFields.add(field)
      }
    }

    if (changedFields.size > 0) {
      pending.set(eventId, {operation: 'update', fields: changedFields})
      setRowDirty(row, true)
    } else {
      pending.delete(eventId)
      setRowDirty(row, false)
    }
    updateSubmitState()
  }

  function findRow(eventId) {
    return [...document.querySelectorAll(
      '#editEventTable tr[data-game-id]')]
      .find((row) => row.dataset.gameId === eventId)
  }

  function setParameter(parameters, key, value) {
    parameters[key] = value
  }

  function patchParameters() {
    const parameters = {}
    const password = document.getElementById('pwInput')
    setParameter(parameters, 'password', password?.value || '')

    for (const [eventId, patch] of pending) {
      setParameter(
        parameters,
        `events[${eventId}][operation]`,
        patch.operation)

      if (patch.operation === 'delete') {
        continue
      }

      const row = findRow(eventId)
      if (!row) {
        continue
      }

      for (const field of patch.fields) {
        const key = `events[${eventId}][${field}]`
        if (field === 'scouters') {
          const values = controlsFor(row, field)
            .map((control) => control.value)
            .filter((value) => value !== '')
          setParameter(parameters, key, values.length > 0 ? values : [''])
        } else {
          setParameter(
            parameters,
            key,
            controlsFor(row, field)[0]?.value || '')
        }
      }
    }

    return parameters
  }

  document.addEventListener('input', (event) => {
    const row = rowFor(event.target)
    const field = event.target?.dataset?.eventField
    if (row && fields.includes(field)) {
      reconcileRow(row)
    }
  })

  document.addEventListener('change', (event) => {
    const row = rowFor(event.target)
    const field = event.target?.dataset?.eventField
    if (row && fields.includes(field)) {
      reconcileRow(row)
    }
  })

  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) {
      return
    }

    const button = target.closest('.deleteButton')
    const row = button?.closest('tr[data-game-id]')
    if (!row) {
      return
    }

    const eventId = row.dataset.gameId
    if (row.dataset.newEvent === 'true') {
      pending.delete(eventId)
    } else {
      pending.set(eventId, {operation: 'delete', fields: new Set()})
    }
    updateSubmitState()
  }, true)

  document.addEventListener('htmx:confirm', (event) => {
    const form = document.getElementById('eventForm')
    if (!form || event.detail?.elt !== form ||
        event.detail?.verb?.toLowerCase() !== 'post' ||
        pending.size < confirmationThreshold) {
      return
    }

    const message = `Du bist dabei, ${pending.size} Änderungen gleichzeitig zu speichern. Möchtest du fortfahren?`
    if (!window.confirm(message)) {
      event.preventDefault()
    }
  })

  document.addEventListener('htmx:configRequest', (event) => {
    const form = document.getElementById('eventForm')
    if (!form || event.detail?.elt !== form ||
        event.detail?.verb?.toLowerCase() !== 'post') {
      return
    }

    event.detail.parameters = patchParameters()
  })

  document.addEventListener('htmx:afterSwap', (event) => {
    if (event.detail?.target?.id !== 'content') {
      return
    }

    pending.clear()
    updateSubmitState()
  })
})()
