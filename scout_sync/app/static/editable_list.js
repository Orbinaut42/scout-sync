EVENTS = []
NAMES = []

function addTableRow(event) {
    if (event == null) {
        var gameId = Date.now().toString()
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

        var gameId = event.id
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

    const $newRow = $('#eventTable').children('.templateRow').clone().removeAttr('class')
    $newRow.data('gameId', gameId)
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

function getTableData() {
    return $('#eventTable').children('tr').not('.templateRow').map((i, row) => {return {
        id: $(row).data('gameId'),
        datetime: Date.parse(`${$(row).children('.dateTd').children('input').val()} ${$(row).children('.timeTd').children('input').val()}`) || 0,
        location: $(row).children('.locationTd').text(),
        league: $(row).children('.leagueTd').text(),
        opponent: $(row).children('.opponentTd').text(),
        scouters: $(row).children('.scouterTd').children('select').map((i, s) => $(s).val()).get().filter(s => s !== '')
    }}).get()
}

function submitEvents() {
    const tableData = getTableData()
    tableData.forEach(d => d.schedule_info = EVENTS.find(e => e.id === d.id)?.schedule_info || null)
    $.ajax(
        '/edit',
        {
            method: 'POST',
            data: JSON.stringify({ password: $('#pwInput').val(), events: tableData }),
            contentType: 'application/json'
        }
    )
    .done(() => {
            $('#submitResponse').text('Ok')
        }
    )
    .fail((data) => {
            if (data.status == 401) $('#submitResponse').text('Passwort falsch')
            else $('#submitResponse').text(`${data.status}: ${data.statusText}`)
        }
    )
}

function updateStatsTable() {
    const categories = {
        c1: /(?<![RNJ])BBL|Euro/,
        c2: /ProB/,
        c3: null
    }
    
    const statsTable = Object.fromEntries(NAMES.map(n => [
        n, Object.fromEntries(Object.keys(categories).map(c => [c, 0]))
    ]))

    for (const game of getTableData()) {
        for (const c in categories) {
            if (!categories[c] || game.league.match(categories[c])) {
                game.scouters.forEach(s => statsTable[s][c] += 1)
                break
            }
        }
    }

    $('#statsTable').children('tr').not('.templateRow').each((i, tr) => {
        const $tr = $(tr)
        const stats = statsTable[$tr.children('.nameTd').text()]
        $tr.children('.cat1Td').text(stats.c1)
        $tr.children('.cat2Td').text(stats.c2)
        $tr.children('.cat3Td').text(stats.c3)
        $tr.children('.sumTd').text(stats.c1 + stats.c2 +stats.c3)
    })
}

$(document).ready(() => {
    $.getJSON('/list/events', (response, status) => {  
        if (status != 'success') {
            throw new Error(status)
        }
        
        EVENTS = response.events
        NAMES = response.names
        
        $('#eventTable').find('select').append(
            $.map(['', ...NAMES], n => $('<option/>', {'value': n}).text(n))
        )

        EVENTS.forEach(addTableRow)
        NAMES.forEach(n => {
            const $newRow = $('#statsTable').children('.templateRow').clone().removeAttr('class')
            $newRow.children('.nameTd').text(n)
            $newRow.appendTo($("#statsTable")).prop('hidden', false)
        })
    })

    new MutationObserver(updateStatsTable).observe($('#eventTable')[0], {childList: true})
    $('#eventTable').on('input', updateStatsTable)
    $('#addRow').on('click', () => addTableRow(null))
    $('#submitEvents').on('click', submitEvents)
})
