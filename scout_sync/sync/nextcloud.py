import datetime
from caldav.davclient import get_davclient
# from caldav.calendarobjectresource import Event
# from caldav.lib.error import NotFoundError
# from icalendar import vCalAddress, Event

# a1 = vCalAddress('mailto:scouting.bbu@gmail.com')
# a1.name = 'ScoutingBBU'

# new_event.add_attendee('mailto:scouting.bbu@gmail.com')

# print(new_event.to_ical().decode("utf-8").replace('\r\n', '\n').strip())


with get_davclient() as client:
    my_principal = client.principal()
    my_calendar = my_principal.calendar()
    for ev in my_calendar.events():

        if 'Event' in ev.component.get('summary') :
            print(ev.data)

    # print(ev.component.get('summary'))

    # my_calendar.save_object(new_event)

    # ev = my_calendar.save_event(
    #     dtstart=datetime.datetime(2025, 12, 5, 13),
    #     dtend=datetime.datetime(2025, 12, 5, 16),
    #     summary="Event 5")

    # my_calendar.save_with_invites(
    #     ev.data,
    #     attendees=['scouting.bbu@gmail.com'])

    # ev.add_organizer()
    # ev.add_attendee(
    #     ('Scouting BBU', 'scouting.bbu@gmail.com'),
    #     cutype='INDIVIDUAL')

    # print(ev.data)
    # ev.save()

    # my_calendar.save()
