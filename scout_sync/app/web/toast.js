(() => {
  'use strict'

  const dismissalDelay = 5000

  function scheduleDismissal(toast) {
    if (!(toast instanceof Element) || toast.dataset.dismissScheduled) {
      return
    }

    toast.dataset.dismissScheduled = 'true'
    setTimeout(() => toast.remove(), dismissalDelay)
  }

  document.addEventListener('htmx:load', (event) => {
    const element = event.detail?.elt
    if (!(element instanceof Element)) {
      return
    }

    if (element.matches('.toast')) {
      scheduleDismissal(element)
    }

    element.querySelectorAll('.toast').forEach(scheduleDismissal)
  })
})()