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
    while (scouters.length < 4) scouters.push('')

    const $newViewRow = $('#viewEventTable').children('.templateRow').clone().removeAttr('class')
    $newViewRow.addClass(date < Date.now() ? 'past' : 'upcoming')
    $newViewRow.children('.viewDateTimeTd').html(`${dateString}<br>${timeString}`)
    $newViewRow.children('.viewLocationTd').text(location || '')
    $newViewRow.children('.viewLeagueTd').text(league || '')
    $newViewRow.children('.viewOpponentTd').text(opponent || '')
    $newViewRow.children('.viewScouterTd').html(scouters.join('<br>'))
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
    $newEditRow.children('.editDateTimeTd').children('input[type="date"]')
        .attr('value', dateString)
        .prop('disabled', !editable)
    $newEditRow.children('.editDateTimeTd').children('input[type="time"]')
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
        return [$newSelect, $('<br>')]
    }))
    $newEditRow.find('.deleteButton')
        .prop('disabled', !editable)
        .on('click', function () {$(this).parents('tr').remove()})
    $newEditRow.appendTo($("#editEventTable")).prop('hidden', false)

    return $newEditRow
}

function reload () {
    $.getJSON('/list/events', (response, status) => {  
        if (status != 'success') {
            throw new Error(status)
        }
        
        EVENTS = response.events.sort((e1, e2) => new Date(e1.datetime) - new Date(e2.datetime))
        NAMES = response.names.sort()
        
        $('#editEventTable').find('select').html('').append(
            $.map(['', ...NAMES], n => $('<option/>', {'value': n}).text(n))
        )

        $('#viewEventTable').children('tr').not('.templateRow').remove()
        $('#editEventTable').children('tr').not('.templateRow').remove()
        $('#statsTable').children('tbody').children('tr').not('.templateRow').remove()
        $('#pwInput').val('')
        $('#submitResponse').text('')

        EVENTS.forEach(addViewTableRow)
        $('tr.upcoming').get()[0].scrollIntoView(alignToTop=true)

        NAMES.forEach(n => {
            const $newRow = $('#statsTable').children('tbody').children('.templateRow').clone().removeAttr('class')
            $newRow.children('.nameTd').text(n)
            $newRow.appendTo($("#statsTable").children("tbody")).prop('hidden', false)
        })
    })

    $('#editToggle').prop('checked', false)
    setEditState()
    setStatsState()
}

function getEditTableData () {
    return $('#editEventTable').children('tr').not('.templateRow').map((i, row) => {return {
        id: $(row).data('gameId'),
        datetime: Date.parse($(row).children('.editDateTimeTd').children('input').map((i, input) => input.value).get().join(' ')),
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
        '/list/edit',
        {
            method: 'POST',
            data: JSON.stringify({ password: $('#pwInput').val(), events: tableData }),
            contentType: 'application/json'
        }
    )
    .done(() => {
            $('#submitResponse').text('Ok')
            $('#pwInput').val('')
            reload()
        }
    )
    .fail((data) => {
            if (data.status == 401) $('#submitResponse').text('Passwort falsch')
            else $('#submitResponse').text(`${data.status}: ${data.statusText}`)
            $('#pwInput').val('')
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

    $('#statsTable').children('tbody').children('tr').not('.templateRow').each((i, tr) => {
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
        $(".viewOnly").fadeOut()
        $(".editOnly").fadeIn()
    } else {
        $(".viewOnly").fadeIn()
        $(".editOnly").fadeOut()
    }
}

function setStatsState () {
    if ($('#statsToggle').is(':checked')) {
        $("#statsTable").fadeIn()
    } else {
        $("#statsTable").fadeOut()
    }
}

$(document).ready(() => {
    new MutationObserver(updateStatsTable).observe($('#editEventTable')[0], {childList: true})
    $('#editEventTable').on('input', updateStatsTable)
    $('#addRow').on('click', () => {
        addEditTableRow(null).get()[0].scrollIntoView(alignToTop=true)
    })
    $('#submitEvents').on('click', submitEvents)
    $('#pwInput').keypress(e => {
        if (e.which == 13) {
            submitEvents()
            return false
        }
    })
    $('#editToggle').on('change', () => {
        if ($('#editToggle').is(':checked')) {
            $('#editEventTable').children('tr').not('.templateRow').remove()
            EVENTS.forEach(addEditTableRow)
        }
        
        setEditState()
    })
    $('#statsToggle').on('change', setStatsState)

    reload()
})

$(window).on("focus", () => {
    if (!$('#editToggle').is(':checked'))
        reload()
})