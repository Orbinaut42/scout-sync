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

    const $newRow = $('#templateRow').clone().removeAttr('id')
    $newRow.children('.dateTd').children('input')
        .attr('value', dateString)
        .prop('disabled', !editable)
    $newRow.children('.timeTd').children('input')
        .attr('value', timeString)
        .prop('disabled', !editable)
    $newRow.children('.locationTd')
        .text(location || '')
        .prop('contenteditable', editable)
    $newRow.children('.leagueTd')
        .text(league || '')
        .prop('contenteditable', editable)
    $newRow.children('.opponentTd')
        .text(opponent || '')
        .prop('contenteditable', editable)
    const $scouterSelectTemplate = $newRow.children('.scouterTd').children('select').detach()
    $newRow.children('.scouterTd').append($.map(scouters, s => {
        const $newSelect = $scouterSelectTemplate.clone()
        $newSelect.children(`option[value='${s}']`).prop('selected', true)
        return $newSelect
    }))
    $newRow.find('.deleteButton')
        .on('click', function () {$(this).parents('tr').remove()})
        .prop('disabled', !editable)
    $newRow.appendTo($("#eventTable")).prop('hidden', false)
}

$(document).ready(() => {
    $.getJSON('/list/events', (response, status) => {  
        if (status != 'success') {
            throw new Error(status)
        }
        
        $('#templateRow').children('.scouterTd').children('select').append(
            $.map(['', ...response.names], n => $('<option/>', {'value': n}).text(n))
        )

        response.events.forEach(addTableRow)
    })

    $('#addRow').on('click', () => addTableRow(null))
})
