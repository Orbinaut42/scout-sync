function addTableData(tr, content) {
    const td = document.createElement('td')
    td.appendChild(document.createTextNode(content || ''))
    tr.appendChild(td)
}

function loadTableContents() {
    fetch('/list/events').then(response => {
        if (!response.ok) {
            throw new Error(response.status)
        }

        const tbody = document.getElementById('eventTable')
        tbody.innerHTML = ''
        response.json().then(events => {
            events.forEach(ev => {
                const tr = document.createElement('tr')
                const date = new Date(ev.datetime)
                tr.className = date < Date.now() ? 'past' : 'upcoming'

                addTableData(tr, date
                    .toLocaleDateString(
                        'de-DE',
                        {'weekday': 'short', 'day': '2-digit', 'month': '2-digit', 'year': '2-digit'})
                    )
                addTableData(tr, date.getHours() || date.setMinutes()
                    ? date.toLocaleTimeString(
                        'de-DE',
                        {'timeStyle': 'short'}
                    )
                    : ''
                )
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
