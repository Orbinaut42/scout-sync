from datetime import datetime, timezone, timedelta
from caldav.davclient import get_davclient

with get_davclient() as client:
    my_principal = client.principal()
    my_calendar = my_principal.calendar()
    for ev in my_calendar.events():
        if 'Event' in ev.component.get('summary'):
            print(ev.data)
            ev.add_organizer()
            ev.add_attendee(
                ('Scouting BBU', 'scouting.bbu@gmail.com'),
                cutype='INDIVIDUAL')
            ev.save(increase_seqno=False)
            print(ev.data)
            ev.load()
            ev.delete()

    # ev = my_calendar.save_event(
    #     dtstart=datetime(2025, 12, 2, 13, tzinfo=timezone(timedelta(hours=2))),
    #     dtend=datetime(2025, 12, 2, 16, tzinfo=timezone(timedelta(hours=2))),
    #     summary="Event caldav",
    #     sequence=0)
