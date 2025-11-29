import datetime
from caldav.davclient import get_davclient
from caldav.lib.error import NotFoundError

with get_davclient() as client:
    my_principal = client.principal()
    try:
        my_calendar = my_principal.calendar()
        for ev in my_calendar.events():
            print(ev.component.get('summary'))

        my_calendar.add_event(
            dtstart=datetime.datetime(2025, 12, 1, 12),
            dtend=datetime.datetime(2025, 12, 1, 16),
            summary="Do the needful"
        )
    except NotFoundError:
        print("You don't seem to have any calendars")
