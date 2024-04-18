SCOUTER_NAMES = [
    '',
    'Andreas',
    'Ralf',
    'Claus'
]

function addTableRow(event) {
    if (event == null) {
        var dateString = ''
        var timeString = ''
        var location = ''
        var league = ''
        var opponent = ''
        var scouters = ['', '', '']
        var editable = true
    } else {
        const date = new Date(event.datetime)
        const year = date.getFullYear().toString().toString().padStart(4, "0")
        const month = (date.getMonth() + 1).toString().padStart(2, "0")
        const day = date.getDate().toString().padStart(2, "0")
        const hour = date.getHours().toString().padStart(2, "0")
        const minute = date.getMinutes().toString().padStart(2, "0")

        var dateString = `${year}-${month}-${day}`
        var timeString = date.getHours() || date.getMinutes()
            ? `${hour}:${minute}`
            : ''
        var location = event.location
        var league = event.league
        var opponent = event.opponent
        var scouters = Array.from(event.scouters)
        while (scouters.length < 3) scouters.push('')
        var editable = event.schedule_info == null
    }

    $('<tr/>').append([
        $('<td/>').append($('<input/>', {
            'type': 'date',
            'value': dateString,
            'disabled': !editable
        })),
        $('<td/>').append($('<input/>', {
            'type': 'time',
            'value':  timeString,
            'disabled': !editable
        })),
        $('<td/>', { 'contenteditable': editable }).text(location || ''),
        $('<td/>', { 'contenteditable': editable }).text(league || ''),
        $('<td/>', { 'contenteditable': editable }).text(opponent || ''),
        $('<td/>').append($.map(scouters, name =>
            $('<select/>').append($.map(SCOUTER_NAMES, n =>
                $('<option/>', {'selected': n === name}).text(n))
            )
        )),
        $('<button/>',  { 'disabled': !editable })
            .text("Spiel löschen")
            .on('click', function () {$(this).parent().remove()})
    ]).appendTo($("#eventTable"))
}

$(document).ready(() => {
    $.getJSON('/list/events', (events, status) => {
        if (status != 'success') {
            throw new Error(status)
        }

        $("#eventTable").html('')
        events.forEach(addTableRow)
    })

    $('#addRow').on('click', () => addTableRow(null))
})
