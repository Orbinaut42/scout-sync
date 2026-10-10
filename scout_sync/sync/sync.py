import logging
import datetime
import requests
import arrow
import json
import time
import vobject
from .google_api import GoogleCalendarAPI
from caldav.davclient import get_calendar  # get_davclient
from ..config import config

logging.basicConfig(
    filename=config.log_file,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO)

logging.getLogger('googleapiclient').setLevel(logging.ERROR)


class Event:
    """Manages conversion between different event representation
    formats (DBB schedule, Google Calendar, JSON)"""

    _emails = config.emails
    _names = {v: k for k, v in config.emails.items()}

    def __init__(
            self, id, datetime,
            location=None,
            league=None,
            opponent=None,
            scouters=None,
            schedule_info=None):
        self.id = str(id)
        self.datetime = datetime
        self.location = location
        self.league = league
        self.opponent = opponent
        self.scouters = scouters
        self.schedule_info = schedule_info

    @classmethod
    def from_calendar_event(cls, event):
        """Create an event from a Google Calendar event"""

        event_extended_properties = event.get('extendedProperties', {}).get('private', {})
        event_id = event_extended_properties.get('matchNo')
        if event_id is None:
            logging.warning(
                f"Invalid event at {event['start'].get('dateTime') or event['start'].get('date')}")
            return

        schedule_info = {
                'match_id': event_extended_properties.get('matchId'),
                'league_id': event_extended_properties.get('leagueId')}
        if schedule_info['match_id'] is None or schedule_info['league_id'] is None:
            schedule_info = None

        scouter_list = []
        for a in event.get('attendees', []):
            if a['responseStatus'] == 'declined':
                continue

            try:
                scouter_list.append(cls._names[a['email']])
            except KeyError:
                logging.warning(
                    f"Unknown email in calendar event at {event['start'].get('dateTime') or event['start'].get('date')}: {a['email']}")  # noqa: E501

        e = cls(
            id=event_id,
            datetime=arrow.get(event['start'].get('dateTime') or event['start'].get('date')),
            location=event.get('location', None),
            league=event.get('summary', '').replace('Scouting ', '') or None,
            opponent=event.get('description', None),
            scouters=scouter_list,
            schedule_info=schedule_info)

        return e

    @classmethod
    def from_vevent(cls, event):
        """Create an event from a vobject VEVENT component
        Events without the Scouting category are ignored"""

        uid_props = event.contents.get('uid')
        dtstart_props = event.contents.get('dtstart')
        dt = dtstart_props[0].value if dtstart_props else None

        categories = {
            str(value).strip()
            for prop in event.contents.get('categories', [])
            for value in (prop.value if isinstance(prop.value, list) else [prop.value])}

        if 'Scouting' not in categories:
            logging.debug(
                f"Ignoring event at {dt if dt else 'unknown time'}: "
                "no Scouting category")
            return

        if not uid_props:
            logging.warning(
                f"Invalid event at {dt if dt else 'unknown time'}")
            return
        uid = uid_props[0].value

        x_match = event.contents.get('x-match-id')
        x_league = event.contents.get('x-league-id')
        schedule_info = {
                'match_id': x_match[0].value if x_match else None,
                'league_id': x_league[0].value if x_league else None}
        if schedule_info['match_id'] is None or schedule_info['league_id'] is None:
            schedule_info = None
        else:
            schedule_info = {
                'match_id': str(schedule_info['match_id']),
                'league_id': str(schedule_info['league_id'])}

        scouter_list = []
        for a in event.contents.get('attendee', []):
            partstat_vals = a.params.get('PARTSTAT') or []
            partstat = str(partstat_vals[0] if partstat_vals else '').upper()
            if partstat == 'DECLINED':
                continue

            email = str(a.value)
            if email.lower().startswith('mailto:'):
                email = email[7:]

            try:
                scouter_list.append(cls._names[email])
            except KeyError:
                logging.warning(
                    f"Unknown email in calendar event at {dt}: {email}")

        if isinstance(dt, datetime.datetime):
            if dt.tzinfo is None:
                event_datetime = arrow.Arrow.fromdatetime(dt, tzinfo=config.timezone)
            else:
                event_datetime = arrow.get(dt)
        elif dt is not None:
            event_datetime = arrow.Arrow.fromdatetime(
                datetime.datetime.combine(dt, datetime.time()), tzinfo=config.timezone)
        else:
            event_datetime = None

        def text(prop):
            props = event.contents.get(prop)
            return None if not props else str(props[0].value)

        league = text('summary') or ''
        e = cls(
            id=str(uid),
            datetime=event_datetime,
            location=text('location'),
            league=league.replace('Scouting ', '') or None,
            opponent=text('description'),
            scouters=scouter_list,
            schedule_info=schedule_info)

        return e

    @classmethod
    def from_DBB_schedule(cls, event, league_name):
        """Create an event from a JSON object (DBB schedule)"""
        try:
            datetime = arrow.get(
                f"{event['kickoffDate']}T{event['kickoffTime']}",
                tzinfo=config.timezone)
        except Exception:
            datetime = arrow.get(2147483648, tzinfo=config.timezone)

        try:
            location_id = event['matchInfo']['spielfeld']['id']
            location = ScheduleHandler.arenas.get(str(location_id))
            if location is None:
                logging.info(f"Event at {datetime}: Unknown arena ID in Schedule: {location_id}")
                location = event['matchInfo']['spielfeld']['bezeichnung']
        except Exception:
            location = None

        try:
            opponent = event['guestTeam']['teamname']
        except Exception:
            opponent = None

        e = cls(
            id=f"{event['ligaData']['seasonId']}_{event['ligaData']['verbandId']}_{event['matchNo']}",  # noqa: E501
            datetime=datetime,
            location=location,
            league=league_name,
            opponent=opponent,
            schedule_info={
                'match_id': str(event['matchId']),
                'league_id': str(event['ligaData']['ligaId'])})

        return e

    @classmethod
    def from_json(cls, event):
        """create an event from a json object"""

        datetime = arrow.get(event.get('datetime'), tzinfo=config.timezone)
        scouter_list = []
        for scouter_name in event.get('scouters') or []:
            if not scouter_name:
                continue
            if scouter_name not in cls._emails:
                logging.warning(
                    f"Unknown scouter name in event at {datetime}: "
                    f"{scouter_name}")
                continue
            scouter_list.append(scouter_name)

        e = cls(
            id=str(event['id']),
            datetime=datetime,
            location=event.get('location') or None,
            league=event.get('league') or None,
            opponent=event.get('opponent') or None,
            scouters=scouter_list,
            schedule_info=event.get('schedule_info'))

        return e

    def as_calendar_event(self):
        """create a representation of the event, that can be passed to the Google Calendar API"""
        event = {}

        event['extendedProperties'] = {'private': {'matchNo': self.id}}
        if self.schedule_info:
            event['extendedProperties']['private'].update({
                'matchId': self.schedule_info.get('match_id'),
                'leagueId': self.schedule_info.get('league_id')})

        event['start'] = {
            'dateTime': self.datetime.isoformat(),
            'timeZone': config.timezone
        }
        event['end'] = {
            'dateTime': self.datetime.shift(hours=2).isoformat(),
            'timeZone': config.timezone
        }

        event['location'] = self.location
        event['summary'] = "Scouting " + (self.league or '')
        event['description'] = self.opponent

        if self.scouters is not None:
            event['attendees'] = []
            for scouter_name in self.scouters:
                email = self._emails.get(scouter_name)
                if email is None:
                    logging.warning(f"Unknown scouter name in event at {self.datetime}: {scouter_name}")  # noqa: E501

                if email not in [None, '']:
                    event['attendees'].append({
                        "email": email,
                        "displayName": scouter_name
                    })

        event['reminders'] = {
            'useDefault': False,
            'overrides': [{
                'method': 'popup',
                'minutes': 360
            }]
        }

        return event

    def as_vevent(self, sequence=0, notify=True):
        """create a vobject VEVENT component for the CalDAV API
        sequence -> int iCalendar SEQUENCE number
        notify -> bool whether attendees should get an invitation (future events)"""

        event = vobject.iCalendar().add('vevent')
        event.add('uid').value = self.id
        event.add('sequence').value = str(sequence)
        event.add('categories').value = ['Scouting']

        start = self.datetime.to(config.timezone)
        dtstart = event.add('dtstart')
        dtstart.value = start.datetime.replace(tzinfo=None)
        dtstart.params['TZID'] = [config.timezone]
        dtend = event.add('dtend')
        dtend.value = start.shift(hours=2).datetime.replace(tzinfo=None)
        dtend.params['TZID'] = [config.timezone]

        event.add('summary').value = 'Scouting ' + (self.league or '')
        if self.location is not None:
            event.add('location').value = self.location
        if self.opponent is not None:
            event.add('description').value = self.opponent

        if self.schedule_info:
            match_id = self.schedule_info.get('match_id')
            league_id = self.schedule_info.get('league_id')
            if match_id is not None:
                event.add('x-match-id').value = str(match_id)
            if league_id is not None:
                event.add('x-league-id').value = str(league_id)

        organizer = config.caldav_username
        if organizer and '@' in organizer:
            org = event.add('organizer')
            org.value = f'mailto:{organizer}'
            org.params['CN'] = [organizer]

        if self.scouters is not None:
            partstat = 'NEEDS-ACTION' if notify else 'ACCEPTED'
            rsvp = 'TRUE' if notify else 'FALSE'
            for scouter_name in self.scouters:
                email = self._emails.get(scouter_name)
                if email is None:
                    logging.warning(f"Unknown scouter name in event at {self.datetime}: {scouter_name}")  # noqa: E501

                if email not in [None, '']:
                    attendee = event.add('attendee')
                    attendee.value = f'mailto:{email}'
                    attendee.params['CN'] = [scouter_name]
                    attendee.params['CUTYPE'] = ['INDIVIDUAL']
                    attendee.params['ROLE'] = ['REQ-PARTICIPANT']
                    attendee.params['PARTSTAT'] = [partstat]
                    attendee.params['RSVP'] = [rsvp]

        alarm = event.add('valarm')
        alarm.add('action').value = 'DISPLAY'
        alarm.add('trigger').value = datetime.timedelta(minutes=-360)
        alarm.add('description').value = 'Scouting'

        return event

    def as_json(self):
        """return a json representation of the event"""
        return {
            'id': self.id,
            'datetime': self.datetime.format() if self.datetime else None,
            'location': self.location,
            'league': self.league,
            'opponent': self.opponent,
            'scouters': self.scouters or [],
            'schedule_info': self.schedule_info}

    def __str__(self):
        info_list = (
            (i or '')
            for i in (
                str(self.id),
                self.datetime.format() if self.datetime else None,
                self.location,
                self.league,
                self.opponent,
                *(self.scouters or [])))

        return ', '.join(info_list)

    def __eq__(self, rhs):
        """Compare two Event objects
        Returns True if all attributes are equal"""
        compare_scouters = self.scouters is not None and rhs.scouters is not None

        return all([
            self.id == rhs.id,
            self.datetime == rhs.datetime,
            self.location == rhs.location,
            self.league == rhs.league,
            self.opponent == rhs.opponent,
            not compare_scouters or (
                all(s in self.scouters for s in rhs.scouters) and
                len(self.scouters) == len(rhs.scouters))])


class CalendarHandler(GoogleCalendarAPI):
    """Manages the communication with the Google Calendar API"""

    def __init__(self, calendar_id):
        super().__init__(calendar_id, config.timezone)
        self._ids = None

    def connect(self):
        try:
            self._connect_to_service()

        except Exception as e:
            logging.error(
                f"Connection to calendar with ID {self._resource_id} failed: {e}")

            return False

        logging.info(f"Connected to calendar: {self._resource_id}")
        return True

    def add_events(self, events):
        if not self._service:
            return

        for ev in events:
            if not ev.datetime:
                logging.warning(f"Can not add event to calendar {ev}: event has no date")
                continue

            self._insert_event(ev.as_calendar_event())
            logging.info(f"Added event to calendar:\n\t\t{ev}")

    def update_events(self, events):
        if not self._service:
            return

        for ev in events:
            cal_id = self._ids.get(ev.id)
            if cal_id is None:
                raise ValueError(f"Can not update event {ev.id}: event is not in calendar!")

            cal_ev = self._get_single_event(cal_id)
            old_ev = Event.from_calendar_event(cal_ev)

            self._update_event(cal_id, ev.as_calendar_event(), cal_ev)
            logging.info(
                f"Updated event in calendar:\n\t-\t{old_ev}\n\t+\t{ev}")

    def delete_events(self, events):
        if not self._service:
            return

        for ev in events:
            cal_id = self._ids.get(ev.id)
            if cal_id is None:
                raise ValueError(f"Can not delete event {ev.id}: event is not in calendar!")

            cal_ev = self._get_single_event(cal_id)
            old_ev = Event.from_calendar_event(cal_ev)

            self._delete_event(cal_id, cal_ev)
            logging.info(f"Deleted event in calendar:\n\t\t{old_ev}")

    def list_events(self):
        if not self._service:
            return

        calendar_events = self._get_all_events()
        self._ids = {}
        events = []
        for ce in calendar_events:
            event = Event.from_calendar_event(ce)

            if event is not None:
                self._ids[event.id] = ce['id']
                events.append(event)

        return events


class CalDavHandler():
    """Manages the communication with a CalDAV API"""

    def __init__(self, calendar_name):
        self._calendar_name = calendar_name
        self._calendar = None
        self._resources = None

    def connect(self):
        calendar = get_calendar(
            url=config.caldav_url,
            username=config.caldav_username,
            password=config.caldav_password,
            calendar_name=self._calendar_name)

        if not calendar:
            logging.error(
                f"Connection to CalDAV calendar {self._calendar_name} failed")

            return False

        if not calendar.client.supports_scheduling():
            logging.warning(
                f"CalDAV server does not support scheduling; "
                f"invitations will not be sent for {self._calendar_name}")

        self._calendar = calendar
        self._resources = {
            event.id: event
            for event in self._calendar.get_events()}

        logging.info(f"Connected to calendar: {self._calendar_name}")

        return True

    def add_events(self, events):
        if not self._is_connected():
            return

        for ev in events:
            if not ev.datetime:
                logging.warning(f"Can not add event to calendar {ev}: event has no date")
                continue

            notify = self._should_notify(ev.datetime)
            resource = self._calendar.add_event(
                self._as_calendar_ical(ev, sequence=0, notify=notify))
            self._resources[ev.id] = resource

            logging.info(f"Added event to calendar:\n\t\t{ev}")

    def update_events(self, events):
        if not self._is_connected():
            return

        for ev in events:
            resource = self._resources.get(ev.id)

            if resource is None:
                raise ValueError(f"Can not update event {ev.id}: event is not in calendar!")

            old_vevent = resource.get_vobject_instance().vevent
            old_ev = Event.from_vevent(old_vevent)

            if old_ev is None:
                logging.warning(
                    f"Can not update event {ev.id}: event is not managed by this app")
                continue

            seq_props = old_vevent.contents.get('sequence')
            sequence = int(seq_props[0].value if seq_props else 0) + 1
            notify = self._should_notify(old_ev.datetime, ev.datetime)

            resource.data = self._as_calendar_ical(ev, sequence=sequence, notify=notify)
            resource.save(increase_seqno=False)

            logging.info(
                f"Updated event in calendar:\n\t-\t{old_ev}\n\t+\t{ev}")

    def delete_events(self, events):
        if not self._is_connected():
            return

        for ev in events:
            resource = self._resources.get(ev.id)

            if resource is None:
                raise ValueError(f"Can not delete event {ev.id}: event is not in calendar!")

            old_vevent = resource.get_vobject_instance().vevent
            old_ev = Event.from_vevent(old_vevent)

            if old_ev is None:
                logging.warning(
                    f"Can not delete event {ev.id}: event is not managed by this app")
                continue

            resource.delete()

            logging.info(f"Deleted event in calendar:\n\t\t{old_ev}")

    def list_events(self):
        if not self._is_connected():
            return

        events = []
        for resource in self._resources.values():
            event = Event.from_vevent(resource.get_vobject_instance().vevent)

            if event is not None:
                events.append(event)

        return events

    def _is_connected(self):
        if self._calendar is None or self._resources is None:
            logging.warning(
                f"CalDAV calendar {self._calendar_name} is not connected")
            return False

        return True

    @staticmethod
    def _should_notify(*datetimes):
        now = arrow.now(config.timezone)
        return any(dt is not None and dt > now for dt in datetimes)

    @staticmethod
    def _as_calendar_ical(event, sequence, notify):
        calendar = vobject.iCalendar()
        calendar.add('prodid').value = '-//Scout Sync//'
        calendar.add('version').value = '2.0'
        calendar.add(event.as_vevent(sequence=sequence, notify=notify))
        return calendar


class ScheduleHandler:
    "manages downloads from the DBB game schedule database"

    arenas = config.schedule_arenas
    _REQUEST_TIMEOUT = config.schedule_request_timeout

    def __init__(self, leagues):
        self._schedule = []
        self._leagues = leagues

    def connect(self):
        api_url = 'https://www.basketball-bund.net/rest'
        schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"
        match_info_url = f"{api_url}/match/id/{{match_id}}/matchInfo"
        self._schedule = []
        self._failed_league_downloads = []
        self._failed_match_downloads = []

        with requests.Session() as s:
            for league in self._leagues:
                # get the complete league schedule
                league_name = league['league_name']
                league_id = league['league_id']
                team_permanent_id = league['team_permanent_id']
                team_season_id = league['team_season_id']
                r = s.get(
                    schedule_url.format(league_id=league_id),
                    timeout=ScheduleHandler._REQUEST_TIMEOUT)

                if r.status_code == 200:
                    try:
                        league_schedule = r.json()
                        if not self._validate_league(league_schedule):
                            raise ValueError()

                    except (json.decoder.JSONDecodeError, ValueError):
                        self._failed_league_downloads.append(str(league_id))
                        logging.warning(f"Can not read schedule for league {league_name}")
                        continue
                else:
                    self._failed_league_downloads.append(str(league_id))
                    logging.warning(f"Can not download schedule for league {league_name} ({r.status_code}: {r.reason})")  # noqa: E501
                    continue

                team_matches = []
                for match in league_schedule['data']['matches']:
                    if not self._validate_match(match):
                        try:
                            match_id = match['matchId']
                        except Exception:
                            match_id = None

                        if match_id is not None:
                            self._failed_match_downloads.append(str(match_id))

                        logging.warning(f"Can not read game {match_id} from league {league_name}")
                        continue

                    if (
                            (team_permanent_id and match['homeTeam']['teamPermanentId'] == team_permanent_id) or  # noqa: E501
                            (team_season_id and match['homeTeam']['seasonTeamId'] == team_season_id)):  # noqa: E501
                        team_matches.append(match['matchId'])

                # get the details for each match
                for match_id in team_matches:
                    r = s.get(
                        match_info_url.format(match_id=match_id),
                        timeout=ScheduleHandler._REQUEST_TIMEOUT)

                    if r.status_code == 200:
                        try:
                            match_info = r.json()
                            if not self._validate_match_info(match_info):
                                raise ValueError()

                        except (json.decoder.JSONDecodeError, ValueError):
                            self._failed_match_downloads.append(str(match_id))
                            logging.warning(f"Can not read game details for game {match_id} for league {league_name}")  # noqa: E501
                            continue
                    else:
                        self._failed_match_downloads.append(str(match_id))
                        logging.warning(f"Can not download game details for game {match_id} for league {league_name} ({r.status_code}: {r.reason})")  # noqa: E501
                        continue

                    self._schedule.append((match_info['data'], league_name))

        logging.info(f"Downloaded {len(self._schedule)} game schedules from {len(self._leagues)} leagues")  # noqa: E501
        return True

    def list_events(self):
        events = []
        for match, league_name in self._schedule:
            cancelled = any([match['abgesagt'], match['verzicht']])

            if not cancelled:
                events.append(Event.from_DBB_schedule(match, league_name))

        return events

    def failed(self, match):
        """Check if the match info was downloaded correctly"""
        return (
            match.schedule_info['match_id'] in self._failed_match_downloads or
            match.schedule_info['league_id'] in self._failed_league_downloads)

    def _validate_league(self, league):
        """Check if all relevant properties of the downloaded league
        are present and readable"""
        try:
            matches = league['data']['matches']
            if matches is not None and not isinstance(matches, list):
                raise TypeError()

        except Exception:
            return False

        return True

    def _validate_match(self, match):
        """Check if all relevant properties of the downloaded match
        are present and readable"""
        try:
            conditions = [
                match['matchId'] is not None,
                isinstance(match['homeTeam'], dict),
                (
                    match['homeTeam']['teamPermanentId'] is not None or
                    match['homeTeam']['seasonTeamId'] is not None)]

            if not all(conditions):
                raise TypeError()

        except Exception:
            return False

        return True

    def _validate_match_info(self, match_info):
        """Check if all relevant properties of the downloaded match info
        are present and readable"""
        try:
            match_info_data = match_info['data']
            conditions = [
                match_info_data['matchNo'] is not None,
                match_info_data['matchId'] is not None,
                match_info_data['ligaData']['ligaId'] is not None,
                match_info_data['ligaData']['verbandId'] is not None,
                match_info_data['abgesagt'] is not None,
                match_info_data['verzicht'] is not None]

            if not all(conditions):
                raise TypeError()

        except Exception:
            return False

        return True


class WebCacheHandler():
    def __init__(self, chache_file_name):
        try:
            with open(chache_file_name, encoding='utf8') as web_cache_file:
                self._events = json.load(web_cache_file)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            self._events = None

    def list_events(self):
        if self._events is not None:
            return [Event.from_json(e) for e in self._events]

    def json_events(self):
        return self._events

    def store_events(self, events):
        with open(config.web_cache_file, 'w', encoding='utf8') as web_cache_file:
            json.dump([e.as_json() for e in events], web_cache_file, ensure_ascii=False)


def sync(source):
    """Synchronise the events from source to the calendar and web cache.
    valid scources are 'schedule' and 'cache'"""

    start_time = time.time()
    logging.info(f"Starting sync from {source}")

    if config.calendar_backend == 'caldav':
        calendar_hdl = CalDavHandler(config.caldav_calendar_name)
    else:
        calendar_hdl = CalendarHandler(config.calendar_id)

    if not calendar_hdl.connect():
        raise RuntimeError('Connection to the calendar failed.')

    cache_hdl = WebCacheHandler(config.web_cache_file)

    if source == 'schedule':
        schedule_leagues = config.schedule_leagues

        schedule_hdl = ScheduleHandler(schedule_leagues)
        if not schedule_hdl.connect():
            raise RuntimeError('DBB schedule download failed.')

        source_hdl = schedule_hdl

    elif source == 'cache':
        source_hdl = cache_hdl

    else:
        raise ValueError(f"Invalid value for source: {source}!")

    source_events = {e.id: e for e in source_hdl.list_events()}
    calendar_events = {e.id: e for e in calendar_hdl.list_events()}

    new_events = []
    update_events = []
    delete_events = []
    all_events = []

    # determine which events to add and update
    for src_id, src_ev in source_events.items():
        if src_id not in calendar_events:
            if src_ev not in new_events:
                new_events.append(src_ev)

        else:
            cal_ev = calendar_events[src_id]
            if src_ev.scouters is None:
                src_ev.scouters = cal_ev.scouters

            if src_ev != cal_ev:
                if src_ev not in update_events:
                    update_events.append(src_ev)

        if src_ev not in all_events:
            all_events.append(src_ev)

    # determine which events to delete
    for cal_id, cal_ev in calendar_events.items():
        if cal_id not in source_events:
            # ignore events that are not part of a DBB schedule or where the download failed
            if source == 'schedule':
                if cal_ev.schedule_info is None or source_hdl.failed(cal_ev):
                    if cal_ev not in all_events:
                        all_events.append(cal_ev)

                    continue

            if cal_ev not in delete_events:
                delete_events.append(cal_ev)

    calendar_hdl.add_events(new_events)
    calendar_hdl.update_events(update_events)
    calendar_hdl.delete_events(delete_events)
    cache_hdl.store_events(all_events)

    end_time = time.time()
    logging.info(f"Sync finished ({(end_time-start_time):.0f}s)")

    return
