EVENTS = []
NAMES = []

function addViewTableRow(event) {
    const date = new Date(event.datetime)
    const dateString = date.toLocaleDateString(
        'de-DE',
        {'weekday': 'short', 'day': '2-digit', 'month': '2-digit', 'year': '2-digit'}
    )
    const timeString = date.getHours() || date.getMinutes()
        ? date.toLocaleTimeString(
            'de-DE',
            {'timeStyle': 'short'}
        )
        : ''
    const location = event.location
    const league = event.league
    const opponent = event.opponent
    const scouters = Array.from(event.scouters)

    const $newViewRow = $('#viewEventTable').children('.templateRow').clone().removeAttr('class')
    $newViewRow.children('.viewDateTd').text(dateString)
    $newViewRow.children('.viewTimeTd').text(timeString)
    $newViewRow.children('.viewLocationTd').text(location || '')
    $newViewRow.children('.viewLeagueTd').text(league || '')
    $newViewRow.children('.viewOpponentTd').text(opponent || '')
    $newViewRow.children('.viewScouterTd').text(scouters.join(' '))
    $newViewRow.appendTo($("#viewEventTable")).prop('hidden', false)
}

function addEditTableRow(event) {
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
    
    const $newEditRow = $('#editEventTable').children('.templateRow').clone().removeAttr('class')
    $newEditRow.data('gameId', gameId)
    $newEditRow.children('.editDateTd').children('input')
        .attr('value', dateString)
        .prop('disabled', !editable)
    $newEditRow.children('.editTimeTd').children('input')
        .attr('value', timeString)
        .prop('disabled', !editable)
    $newEditRow.children('.editLocationTd')
        .text(location || '')
        .prop('contenteditable', editable)
    $newEditRow.children('.editLeagueTd')
        .text(league || '')
        .prop('contenteditable', editable)
    $newEditRow.children('.editOpponentTd')
        .text(opponent || '')
        .prop('contenteditable', editable)
    const $scouterSelectTemplate = $newEditRow.children('.editScouterTd').children('select').detach()
    $newEditRow.children('.editScouterTd').append($.map(scouters, s => {
        const $newSelect = $scouterSelectTemplate.clone()
        $newSelect.children(`option[value='${s}']`).prop('selected', true)
        return $newSelect
    }))
    $newEditRow.find('.deleteButton')
        .prop('disabled', !editable)
        .on('click', function () {$(this).parents('tr').remove()})
    $newEditRow.appendTo($("#editEventTable")).prop('hidden', false)
}

function reload () {
    if ($('#editToggle').is(':checked')) return

    console.log('reloda')
    $.getJSON('/list/events', (response, status) => {  
        if (status != 'success') {
            throw new Error(status)
        }
        
        EVENTS = response.events
        NAMES = response.names
        
        $('#editEventTable').find('select').html('').append(
            $.map(['', ...NAMES], n => $('<option/>', {'value': n}).text(n))
        )

        $('#viewEventTable').children('tr').not('.templateRow').remove()
        $('#editEventTable').children('tr').not('.templateRow').remove()
        $('#statsTable').children('tr').not('.templateRow').remove()

        EVENTS.forEach(addViewTableRow)
        NAMES.forEach(n => {
            const $newRow = $('#statsTable').children('.templateRow').clone().removeAttr('class')
            $newRow.children('.nameTd').text(n)
            $newRow.appendTo($("#statsTable")).prop('hidden', false)
        })
    })

    setEditState()
}

function getEditTableData () {
    return $('#editEventTable').children('tr').not('.templateRow').map((i, row) => {return {
        id: $(row).data('gameId'),
        datetime: Date.parse(`${$(row).children('.dateTd').children('input').val()} ${$(row).children('.timeTd').children('input').val()}`) || 0,
        location: $(row).children('.editLocationTd').text(),
        league: $(row).children('.editLeagueTd').text(),
        opponent: $(row).children('.editOpponentTd').text(),
        scouters: $(row).children('.editScouterTd').children('select').map((i, s) => $(s).val()).get().filter(s => s !== '')
    }}).get()
}

function submitEvents() {
    const tableData = getEditTableData()
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

    for (const game of getEditTableData()) {
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

function setEditState() {
    if ($('#editToggle').is(':checked')) {
        $(".viewOnly").hide()
        $(".editOnly").show()
    } else {
        $(".viewOnly").show()
        $(".editOnly").hide()
    }
}

$(document).ready(() => {
    new MutationObserver(updateStatsTable).observe($('#editEventTable')[0], {childList: true})
    $('#editEventTable').on('input', updateStatsTable)
    $('#addRow').on('click', () => {
        addEditTableRow(null)
    })
    $('#submitEvents').on('click', submitEvents)
    $('#editToggle').prop('checked', false)
    $('#editToggle').on('change', () => {
        $('#editEventTable').children('tr').not('.templateRow').remove()
        EVENTS.forEach(addEditTableRow)
        setEditState()
    })

    reload()
})

$(document).on("focus", reload)