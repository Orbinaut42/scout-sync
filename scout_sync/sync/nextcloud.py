# import os
# import vobject

# from datetime import datetime, timezone, timedelta
# from caldav.davclient import get_davclient

from .sync import CalDavHandler

calendar = CalDavHandler()

with calendar.connect():
    for ev in calendar.list_events():
        print()



# from . import carddav

# dav = carddav.PyCardDAV(
#     resource=os.getenv('CARDDAV_URL'),
#     user=os.getenv('CALDAV_USERNAME'),
#     passwd=os.getenv('CALDAV_PASSWORD'))

# abook = dav.get_abook()
# href = list(abook.keys())[42]
# card = dav.get_vcard(href)
# vc = vobject.readOne(card.decode('utf-8'))
# name = vc.fn.value
# email = vc.email.value
# print(name, email)


# with get_davclient() as client:
#     my_principal = client.principal()
#     my_calendar = my_principal.calendar()
#     for ev in my_calendar.events():
#         if 'Event' in ev.component.get('summary'):
#             print(ev.data)
#             ev.add_organizer()
#             ev.add_attendee(
#                 ('Scouting BBU', 'scouting.bbu@gmail.com'),
#                 cutype='INDIVIDUAL')
#             ev.save(increase_seqno=False)
#             print(ev.data)
#             ev.load()
#             ev.delete()

#     ev = my_calendar.save_event(
#         dtstart=datetime(2025, 12, 2, 13, tzinfo=timezone(timedelta(hours=2))),
#         dtend=datetime(2025, 12, 2, 16, tzinfo=timezone(timedelta(hours=2))),
#         summary="Event caldav",
#         sequence=0)
