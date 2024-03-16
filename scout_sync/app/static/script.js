function addTableData(tr, content) {
    const td = document.createElement('td')
    td.appendChild(document.createTextNode(content))
    tr.appendChild(td)
}

document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
        fetch('/list/events').then(response => {
            if (!response.ok) {
                throw new Error(response.status)
            }

            const tbody = document.getElementById('eventTable')
            tbody.innerHTML = ''
            response.json().then(events => {
                events.forEach(ev => {
                    const tr = document.createElement('tr')
                    tr.class = ev.datetime < Date.now() ? 'past' : 'upcoming'
                    addTableData(tr, ev.datetime)
                    addTableData(tr, ev.datetime)
                    addTableData(tr, ev.location)
                    addTableData(tr, ev.league)
                    addTableData(tr, ev.opponent)
                    addTableData(tr, ev.scouter1)
                    addTableData(tr, ev.scouter2)
                    addTableData(tr, ev.scouter3)
                    tbody.appendChild(tr)
                })
            })
        })
    }
})
