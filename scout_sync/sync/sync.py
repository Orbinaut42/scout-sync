import logging
import requests
import arrow
import json
import time
from .google_api import GoogleCalendarAPI
from ..config import config

logging.basicConfig(
    filename=config.get('COMMON', 'log_file'),
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO)

logging.getLogger('googleapiclient').setLevel(logging.ERROR)

TIMEZONE = config.get('COMMON', 'timezone')
SIMULATE = config.getboolean('COMMON', 'simulate')


class Event:
    """Manages conversion between different event representation formats (DBB schedule, Google Calendar, JSON)"""

    __emails = {k: v for k, v in config.items('EMAILS')}
    __names = {v: k for k, v in config.items('EMAILS')}

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

        scouter_list = []
        for a in event.get('attendees', []):
            if a['responseStatus'] == 'declined':
                continue

            try:
                scouter_list.append(cls.__names[a['email']])
            except KeyError:
                logging.warning(
                    f"Unknown email in calendar event at {e.datetime}: {a['email']}")

        event_extended_properties = event.get('extendedProperties', {}).get('private', {})
        schedule_info = {
                'match_id': event_extended_properties.get('matchId'),
                'league_id': event_extended_properties.get('leagueId')}
        if schedule_info['match_id'] is None and schedule_info['match_id'] is None:
            schedule_info = None

        e = cls(
            id = event_extended_properties.get('matchNo'),
            datetime = arrow.get(event['start']['dateTime']),
            location = event.get('location', None),
            league = event.get('summary', '').replace('Scouting ', '') or None,
            opponent = event.get('description', None),
            scouters = scouter_list,
            schedule_info = schedule_info)

        if not e.league:
            logging.warning(f"Calendar event at {e.datetime} has no league")

        return e

    @classmethod
    def from_DBB_schedule(cls, event, league_name):
        """Create an event from a JSON object (DBB schedule)"""
        try:
            datetime = arrow.get(f"{event['kickoffDate']}T{event['kickoffTime']}", tzinfo=TIMEZONE)
        except:
            datetime = arrow.get(2147483648, tzinfo=TIMEZONE)
        
        try:
            location_id = event['matchInfo']['spielfeld']['id']
            location = ScheduleHandler.arenas.get(str(location_id))
            if location is None:
                logging.warning(f"Event at {datetime}: Unknown arena ID in Schedule: {location_id}")
                location = event['matchInfo']['spielfeld']['bezeichnung']
        except:
            location = None

        try:
            opponent = event['guestTeam']['teamname']
        except:
            opponent = None

        e = cls(
            id = event['matchNo'],
            datetime = datetime,
            location = location,
            league = league_name,
            opponent = opponent,
            schedule_info = {
                'match_id': str(event['matchId']),
                'league_id': str(event['ligaData']['ligaId'])})
            
        return e

    def as_calendar_event(self):
        """create a representation of the event, that can be passed to the Google Calendar API"""
        event = {}

        event['extendedProperties'] = {'private': {'matchNo': self.id}}
        if self.schedule_info:
            event['extendedProperties']['private'].update({
                'matchId': self.schedule_info.get('match_id'),
                'leagueId': self.schedule_info.get('league_id')})
            
        if self.datetime:
            event['start'] = {
                'dateTime': self.datetime.isoformat(),
                'timeZone': TIMEZONE
            }
            event['end'] = {
                'dateTime': self.datetime.shift(hours=2).isoformat(),
                'timeZone': TIMEZONE
            }

        else:
            logging.warning('Can not create calendar event: event has no date')
            return None

        event['location'] = self.location
        event['summary'] = "Scouting " + self.league
        event['description'] = self.opponent

        if self.scouters is not None:
            event['attendees'] = []
            for scouter in self.scouters:
                try:
                    event['attendees'].append({
                        "email": self.__emails[scouter],
                        "displayName": scouter
                    })

                except KeyError:
                    logging.warning(
                        f"Unknown scouter name in event at {self.datetime}: {scouter}"
                    )

        event['reminders'] = {
            'useDefault': False,
            'overrides': [{
                'method': 'popup',
                'minutes': 360
            }]
        }

        return event

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
    
    # def to_json(self):
    #     return {
    #         'id': self.id,
    #         'datetime': self.datetime.format() if self.datetime else None,
    #         'location': self.location,
    #         'league': self.league,
    #         'opponent': self.opponent,
    #         'scouter1': self.scouter1,
    #         'scouter2': self.scouter2,
    #         'scouter3': self.scouter3}

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
            all(s in self.scouters for s in rhs.scouters) or not compare_scouters,
            len(self.scouters) == len(rhs.scouters) or not compare_scouters
        ])


class CalendarHandler(GoogleCalendarAPI):
    """Manages the communtcation with the Google Calendar API"""

    def __init__(self, calendar_id):
        super().__init__(calendar_id, TIMEZONE, SIMULATE)

    def connect(self):
        try:
            self._connect_to_service()

        except Exception as e:
            logging.error(
                f"Connection to calendar with ID {self._resource_id} failed: {e}"
            )
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
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Added event to calendar:\n\t\t{ev}"
            )

    def update_events(self, events):
        if not self._service:
            return

        for id in events:
            cal_ev = self._get_single_event(id)
            old_ev = Event.from_calendar_event(cal_ev)
            new_ev = events[id]
            if new_ev.scouters is None:
                new_ev.scouters = old_ev.scouters

            self._update_event(id, cal_ev, new_ev.as_calendar_event())
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Updated event in calendar:\n\t-\t{old_ev}\n\t+\t{new_ev}"
            )

    def delete_events(self, ids):
        if not self._service:
            return

        for id in ids:
            cal_ev = self._get_single_event(id)
            old_ev = Event.from_calendar_event(cal_ev)

            self._delete_event(id, cal_ev)
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Deleted event in calendar:\n\t\t{old_ev}"
            )

    def list_events(self):
        if not self._service:
            return

        ev_list = self._get_all_events()
        return {ev['id']: Event.from_calendar_event(ev) for ev in ev_list}


class ScheduleHandler:
    "manages downloads from the DBB game schedule database"

    arenas = dict(config['SCHEDULE_ARENAS'])
    __REQUEST_TIMEOUT = config.getint('COMMON', 'schedule_request_timeout')

    def __init__(self, leagues):
        self.__schedule = []
        self.__leagues = [
            dict(zip(['league_name', 'league_id', 'team_permanent_id', 'team_season_id'], l))
            for l in leagues]

    def connect(self):
        api_url = 'https://www.basketball-bund.net/rest'
        schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"
        match_info_url = f"{api_url}/match/id/{{match_id}}/matchInfo"
        self.__schedule = []
        self.__failed_league_downloads = []
        self.__failed_match_downloads = []

        with requests.Session() as s:
            for league in self.__leagues:
                # get the complete league schedule
                league_name, league_id, team_permanent_id, team_season_id = league.values()
                r = s.get(
                    schedule_url.format(league_id=league_id),
                    timeout=ScheduleHandler.__REQUEST_TIMEOUT)

                if r.status_code == 200:
                    try:
                        league_schedule = r.json()
                        if not self.__validate_league(league_schedule):
                            raise ValueError()

                    except (json.decoder.JSONDecodeError, ValueError):
                        self.__failed_league_downloads.append(str(league_id))
                        logging.warning(f"Can not read schedule for league {league_name}")
                        continue
                else:
                    self.__failed_league_downloads.append(str(league_id))
                    logging.warning(f"Can not download schedule for league {league_name} ({r.status_code}: {r.reason})")
                    continue
                
                team_matches = []
                for match in league_schedule['data']['matches']:
                    if not self.__validate_match(match):
                        try:
                            match_id = match['matchId']
                        except:
                            match_id = None

                        if match_id is not None:
                            self.__failed_match_downloads.append(str(match_id))

                        logging.warning(f"Can not read game {match_id} from league {league_name}")
                        continue

                    if (
                            (team_permanent_id and match['homeTeam']['teamPermanentId'] == team_permanent_id) or
                            (team_season_id and match['homeTeam']['seasonTeamId'] == team_season_id)):
                        team_matches.append(match['matchId'])
                   
                # get the details for each match
                for match_id in team_matches:
                    r = s.get(
                        match_info_url.format(match_id=match_id),
                        timeout=ScheduleHandler.__REQUEST_TIMEOUT)

                    if r.status_code == 200:
                        try:
                            match_info = r.json()
                            if not self.__validate_match_info(match_info):
                                raise ValueError()
                            
                        except (json.decoder.JSONDecodeError, ValueError):
                            self.__failed_match_downloads.append(str(match_id))
                            logging.warning(f"Can not read game details for game {match_id} for league {league_name}")
                            continue
                    else:
                        self.__failed_match_downloads.append(str(match_id))
                        logging.warning(f"Can not download game details for game {match_id} for league {league_name} ({r.status_code}: {r.reason})")
                        continue

                    self.__schedule.append((match_info['data'], league_name))

        logging.info(f"Downloaded {len(self.__schedule)} game schedules from {len(self.__leagues)} leagues")
        return True

    def list_events(self):
        events = []
        for match, league_name in self.__schedule:
            cancelled = any([match['abgesagt'], match['verzicht']])

            if not cancelled:
                events.append(Event.from_DBB_schedule(match, league_name))

        return {i: event for i, event in enumerate(events)}

    def failed(self, match):
        """Check if the match info was downloaded correctly"""
        return (
            match.schedule_info['match_id'] in self.__failed_match_downloads or
            match.schedule_info['league_id'] in self.__failed_league_downloads)

    def __validate_league(self, league):
        """Check if all relevant properties of the downloaded league
        are present and readable"""
        try:
            matches = league['data']['matches']
            if matches is not None and not isinstance(matches, list):
                raise TypeError()
        
        except:
            return False

        return True

    def __validate_match(self, match):
        """Check if all relevant properties of the downloaded match
        are present and readable"""
        try:
            conditions = [
                match['matchId'] is not None,
                isinstance(match['homeTeam'], dict),
                    (match['homeTeam']['teamPermanentId'] is not None or
                    match['homeTeam']['seasonTeamId'] is not None)]
            
            if not all(conditions):
                raise TypeError()

        except:
            return False
        
        return True
    
    def __validate_match_info(self, match_info):
        """Check if all relevant properties of the downloaded match info
        are present and readable"""
        try:
            match_info_data = match_info['data']
            conditions = [
                match_info_data['matchNo'] is not None,
                match_info_data['matchId'] is not None,
                match_info_data['ligaData']['ligaId'] is not None,
                match_info_data['abgesagt'] is not None,
                match_info_data['verzicht'] is not None]
            
            if not all(conditions):
                raise TypeError()

        except:
            return False
        
        return True

def sync(source, dest):
    """Start the syncronisation from 'source' to 'dest'
    Allowed values for source are: schedule, calendar
    Allowed values for destination are: calendar"""

    logging.info(f"Starting sync from {source} to {dest}")

    start_time = time.time()

    schedule_leagues = [
        config.getlist('SCHEDULE_LEAGUES', o)
        for o in config['SCHEDULE_LEAGUES'].keys()]
    
    handler = {
        'calendar': (CalendarHandler, config.get('CALENDAR', 'id')),
        'schedule': (ScheduleHandler, schedule_leagues)}
    
    source_hdl = handler[source][0](*handler[source][1:])
    dest_hdl = handler[dest][0](*handler[dest][1:])

    if not (source_hdl.connect() and dest_hdl.connect()):
        raise RuntimeError('Connection to the target failed.')

    source_events = source_hdl.list_events().values()
    dest_events = dest_hdl.list_events()

    new_events = []
    update_events = {}
    delete_events = list(dest_events.keys())

    if isinstance(source_hdl, ScheduleHandler):
        # ignore events that are not part of a DBB schedule or where the download failed
        for ev_id, ev in dest_events.items():
            if ev.schedule_info is None or source_hdl.failed(ev):
                delete_events.remove(ev_id)

    # determine which events to add, delete and update
    for ev in source_events:
        for event_id in dest_events:
            if ev.id == dest_events[event_id].id:
                if ev == dest_events[event_id]:
                    if event_id in delete_events:
                        delete_events.remove(event_id)

                    break

                else:
                    if event_id not in update_events:
                        update_events[event_id] = ev

                    if event_id in delete_events:
                        delete_events.remove(event_id)

                    break
        else:
            if ev not in new_events:
                new_events.append(ev)

    dest_hdl.add_events(new_events)
    dest_hdl.update_events(update_events)
    dest_hdl.delete_events(delete_events)

    end_time = time.time()
    logging.info(f"Sync finished ({(end_time-start_time):.0f}s)")

    if isinstance(dest_hdl, CalendarHandler):
        # return the current list of events
        return dest_hdl.list_events()

    return True
