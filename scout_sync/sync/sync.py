import logging
import requests
import arrow
import json
import time
import pickle
from .google_api import GoogleCalendarAPI, GoogleSheetsAPI
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
    """Manages conversion between different event representation formats (JSON schedule, Google Calendar, Google Spreadsheet, ODS Table"""

    __emails = {k: v for k, v in config.items('EMAILS')}
    __names = {v: k for k, v in config.items('EMAILS')}

    def __init__(
            self, id, datetime,
            location=None,
            league=None,
            opponent=None,
            scouter1=None,
            scouter2=None,
            scouter3=None):
        self.id = str(id)
        self.datetime = datetime
        self.location = location
        self.league = league
        self.opponent = opponent
        self.scouter1 = scouter1
        self.scouter2 = scouter2
        self.scouter3 = scouter3
        self.has_scouters = any([self.scouter1, self.scouter2, self.scouter3])

    @classmethod
    def from_gsheets_table_row(cls, row, captions):
        """Create an event from a Google Sheets row"""
        row_vals = {cap: value for value, cap in zip(row, captions) if cap}
        if row_vals.get('ID') in [None, '']:
            logging.warning(f"Event without ID in table!")

        if row_vals['Zeit'] == '':
            row_vals['Zeit'] = 0

        serial_date = None
        if isinstance(row_vals['Datum'], (int, float)):
            serial_date = row_vals['Datum']
        else:
            logging.warning(f"Invalid date in table: {row_vals['Datum']}")

        if isinstance(row_vals['Zeit'], (int, float)):
            if serial_date is not None:
                serial_date += row_vals['Zeit']
        else:
            logging.warning(f"Invalid time in table: {row_vals['Zeit']}")

        e = cls(
            id = row_vals.get('ID'),
            datetime = (GSheetsTableHandler.serial_to_datetime(
                serial_date, TIMEZONE) if serial_date is not None else None),
            location = row_vals.get('Halle') or None,
            league = row_vals.get('Liga'),
            opponent = row_vals.get('Gegner'),
            scouter1 = row_vals.get('Scouter1'),
            scouter2 = row_vals.get('Scouter2'),
            scouter3 = row_vals.get('Scouter3'))
        
        e.has_scouters = True

        return e

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

        e = cls(
            id = event['id'],
            datetime = arrow.get(event['start']['dateTime']),
            location = event.get('location', None),
            league = event.get('summary', '').replace('Scouting ', '') or None,
            opponent = event.get('description', None),
            scouter1 = (scouter_list[0] if len(scouter_list) > 0 else None),
            scouter2 = (scouter_list[1] if len(scouter_list) > 1 else None),
            scouter3 = (scouter_list[2] if len(scouter_list) > 2 else None))

        e.has_scouters = True

        if not e.league:
            logging.warning(f"Calendar event at {e.datetime} has no league")

        return e

    @classmethod
    def from_JSON_schedule(cls, event, league_name):
        """Create an event from a JSON object (DBB schedule)"""
        try:
            datetime = arrow.get(f'{event["kickoffDate"]}T{event["kickoffTime"]}', tzinfo=TIMEZONE)
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
            opponent = ''

        e = cls(
            id = event["matchId"],
            datetime = datetime,
            location = location,
            league = league_name,
            opponent = opponent)
        
        e.has_scouters = False
            
        return e

    def as_calendar_event(self):
        """create a representation of the event, that can be passed to the Google Calendar API"""

        event = {}
        event['id'] = self.id
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

        event['attendees'] = []
        scouterlist = [self.scouter1, self.scouter2, self.scouter3]

        for scouter in [s for s in scouterlist if s and s.strip()]:
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

    def as_gsheets_table_row(self, captions):
        """create a representation of the event, that can be passed to the Google Sheets API"""

        serial = GSheetsTableHandler.datetime_to_serial(self.datetime)
        atts = {
            'ID': self.id,
            'Datum': int(serial),
            'Zeit': (serial - int(serial)) or None,
            'Halle': self.location,
            'Liga': self.league,
            'Gegner': self.opponent,
            'Scouter1': self.scouter1,
            'Scouter2': self.scouter2,
            'Scouter3': self.scouter3
        }

        values = [atts[key] for key in captions]
        return values

    def __str__(self):
        info_list = (
            (i or '')
            for i in (
                str(self.id),
                self.datetime.format() if self.datetime else None,
                self.location,
                self.league,
                self.opponent,
                self.scouter1,
                self.scouter2,
                self.scouter3))
        return ', '.join(info_list)
    
    def to_json(self):
        return {
            'id': self.id,
            'datetime': self.datetime.format() if self.datetime else None,
            'location': self.location,
            'league': self.league,
            'opponent': self.opponent,
            'scouter1': self.scouter1,
            'scouter2': self.scouter2,
            'scouter3': self.scouter3}

    def is_same(self, event):
        """Compare two Event objects
        Returns True if date (not time), league and opponent are equal"""

        self_date = self.datetime.date() if self.datetime else None
        event_date = event.datetime.date() if event.datetime else None
        return all([
            self.league == event.league, self_date == event_date,
            self.opponent == event.opponent
        ])

    def __eq__(self, event):
        """Compare two Event objects
        Returns True if all attributes are equal"""

        self_scouter_list = [self.scouter1, self.scouter2, self.scouter3]
        event_scouter_list = [event.scouter1, event.scouter2, event.scouter3]

        if not (self.has_scouters and event.has_scouters):
            self_scouter_list = event_scouter_list

        return all([
            self.league == event.league, self.datetime == event.datetime,
            self.opponent == event.opponent, self.location == event.location,
            all(s in self_scouter_list for s in event_scouter_list),
            all(s in event_scouter_list for s in self_scouter_list)
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
                logging.warning(
                    f"Can not add event to calendar {ev}: event has no date")
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
            if not new_ev.has_scouters:
                new_ev.scouter1 = old_ev.scouter1
                new_ev.scouter2 = old_ev.scouter2
                new_ev.scouter3 = old_ev.scouter3
                new_ev.has_scouters = True

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


class GSheetsTableHandler(GoogleSheetsAPI):
    """Manages the communication with the Google Calendar API"""

    __captions_row = int(
        config.get('GSHEETS_TABLE', 'captions_row', fallback=None) or 0)

    def __init__(self, spredsheet_id, sheet_name, sheet_id):
        super().__init__(spredsheet_id, sheet_name, sheet_id, TIMEZONE,
                         SIMULATE)
        self.__captions = []
        self.__index = {}
        self.__ids = [
        ]  # keeps track of which event is in which row of the sheet

    def connect(self):
        try:
            self._connect_to_service()
            for cell in self._get_range(self.__captions_row, dims=1):
                self.__captions.extend([cell] if cell != 'Scouter' else
                                       ['Scouter1', 'Scouter2', 'Scouter3'])

            while self.__captions and not self.__captions[-1]:
                del self.__captions[-1]

            table_range = self._get_range(self.__captions_row + 1,
                                          9999,
                                          dims=2)
            self.__ids = [None] * self.__captions_row
            for id, row in enumerate(table_range):
                if any(row):
                    self.__index[id] = row
                    self.__ids.append(id)
                else:
                    self.__ids.append(None)

        except Exception as e:
            logging.error(
                f"Connection to Google spreadsheet with ID {self._resource_id} failed: {e}"
            )
            return False

        logging.info(f"Connected to Google spreadsheet: {self._resource_id}")
        return True

    def add_events(self, events):
        if not self._service or not events:
            return

        date_index = self.__captions.index('Datum')
        time_index = self.__captions.index('Zeit')
        insert_events = []
        for ev in events:
            for id, row in self.__index.items():
                date_entry = row[date_index]
                time_entry = row[time_index]
                date = GoogleSheetsAPI.serial_to_datetime(
                    (date_entry if isinstance(date_entry,
                                              (float, int)) else 0) +
                    (time_entry if isinstance(time_entry,
                                              (float, int)) else 0), TIMEZONE)
                if date > (ev.datetime or arrow.Arrow(9999)):
                    row_no = self.__ids.index(id)
                    break
            else:
                row_no = len(self.__ids)

            insert_events.append(
                (row_no, ev.as_gsheets_table_row(self.__captions)))

        # sort by date in reverse order, so later insertions will be in the correct row
        insert_events.sort(key=lambda e: e[1][date_index] +
                           (e[1][time_index] or 0),
                           reverse=True)
        self._insert_rows(insert_events)
        for row_no, event in insert_events:
            new_id = max((self.__index.keys() or [-1])) + 1
            self.__index[new_id] = event
            self.__ids.insert(row_no, new_id)

        for ev in events:
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Added event to table:\n\t\t{ev}"
            )

    def update_events(self, events):
        if not self._service or not events:
            return

        update_events = [{
            'id':
            id,
            'row':
            self.__ids.index(id),
            'old_event':
            Event.from_gsheets_table_row(self.__index[id], self.__captions),
            'new_event':
            event
        } for id, event in events.items()]

        for event in update_events:
            if not event['new_event'].has_scouters:
                event['new_event'].scouter1 = event['old_event'].scouter1
                event['new_event'].scouter2 = event['old_event'].scouter1
                event['new_event'].scouter3 = event['old_event'].scouter1
                event['new_event'].has_scouters = True

        self._update_rows([
            (ev['row'], ev['new_event'].as_gsheets_table_row(self.__captions))
            for ev in update_events
        ])

        for ev in update_events:
            self.__index[ev['id']] = ev['new_event'].as_gsheets_table_row(
                self.__captions)
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Updated event in table:\n\t-\t{ev['old_event']}\n\t+\t{ev['new_event']}"
            )

    def delete_events(self, event_ids):
        if not self._service or not event_ids:
            return

        delete_events = [self.__ids.index(id) for id in event_ids]
        # sort by date in reverse order, so later deletions will be in the correct row
        delete_events.sort(reverse=True)
        self._delete_rows(delete_events)

        for id in event_ids:
            event = Event.from_gsheets_table_row(self.__index[id],
                                                 self.__captions)
            del self.__index[id]
            self.__ids.remove(id)
            logging.info(
                f"{'(SIMULATED) ' if SIMULATE else ''}Deleted event in table:\n\t\t{event}"
            )

    def list_events(self):
        if not self._service:
            return

        try:
            events = {
                i: Event.from_gsheets_table_row(row, self.__captions)
                for i, row in self.__index.items()
            }

        except (TypeError, ValueError) as e:
            logging.warning(f"Can not create event: {e}")

        return events


class ScheduleHandler:
    "manages downloads from the DBB game schedule database"

    arenas = dict(config['SCHEDULE_ARENAS'])
    __REQUEST_TIMEOUT = config.getint('COMMON', 'schedule_request_timeout')
    __LEAGUES_CACHE_FILE = 'schedule_leagues.cache'

    def __init__(self, leagues):
        self.__schedule = []
        self.__leagues = [
            dict(
                zip([
                    'league_name', 'league_id', 'team_permanent_id',
                    'team_season_id'
                ], l)) for l in leagues
        ]

    def connect(self):
        api_url = 'https://www.basketball-bund.net/rest'
        schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"
        match_info_url = f"{api_url}/match/id/{{match_id}}/matchInfo"
        self.__schedule = []
        self.__failed_league_downloads = []
        self.__failed_match_downloads = []

        
        try:
            with open(self.__LEAGUES_CACHE_FILE, 'rb') as f:
                match_leagues = pickle.load(f)
        except FileNotFoundError:
            match_leagues = {}
        
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
                        self.__failed_league_downloads.append(league_id)
                        logging.error(f"Can not read schedule for league {league_name}")
                        continue
                else:
                    self.__failed_league_downloads.append(league_id)
                    logging.error(f"Can not download schedule for league {league_name} ({r.status_code}: {r.reason})")
                    continue

                
                team_matches = []
                for match in league_schedule['data']['matches']:
                    if not self.__validate_match(match):
                        try:
                            match_id = match['matchId']
                        except:
                            match_id = None

                        if match_id is not None:
                            self.__failed_match_downloads.append(match_id)

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
                            
                        except (json.decoder.JSONDecodeError):
                            self.__failed_match_downloads.append(match_id)
                            logging.error(f"Can not read game details for game {match_id} for league {league_name}")
                            continue
                    else:
                        self.__failed_match_downloads.append(match_id)
                        logging.error(f"Can not download game details for game {match_id} for league {league_name} ({r.status_code}: {r.reason})")
                        continue

                    self.__schedule.append((match_info['data'], league_name))
                    match_leagues[match_id] = league_id

        
        with open(self.__LEAGUES_CACHE_FILE, 'wb') as f:
            pickle.dump(match_leagues, f)

        logging.info(f"Downloaded {len(self.__schedule)} game schedules from {len(self.__leagues)} leagues")
        return True

    def list_events(self):
        events = []
        for match, league_name in self.__schedule:
            cancelled = any([match['abgesagt'], match['verzicht']])

            if not cancelled:
                events.append(Event.from_JSON_schedule(match, league_name))

        return {i: event for i, event in enumerate(events)}

    def failed(self, match_id):
        """Check if the the match info was downloaded correctly"""
        if match_id in self.__failed_match_downloads:
            return True
        
        match_leages = pickle.load(self.__LEAGUES_CACHE_FILE)
        if match_leages[match_id] in self.__failed_league_downloads:
            return True

        return False
    
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
                match_info_data['matchId'] is not None,
                match_info_data['abgesagt'] is not None,
                match_info_data['verzicht'] is not None]
            
            if not all(conditions):
                raise TypeError()

        except:
            return False
        
        return True

def sync(source, dest):
    """Start the syncronisation from 'source' to 'dest'
    Allowed values for source are: schedule, calendar, table
    Allowed values for destination are: calendar, table"""

    logging.info(f"Starting sync from {source} to {dest}")

    start_time = time.time()

    table_handler = (GSheetsTableHandler,
                        config.get('GSHEETS_TABLE', 'id'),
                        config.get('GSHEETS_TABLE',
                                'sheet_name',
                                fallback=None),
                        config.get('GSHEETS_TABLE', 'sheet_id',
                                fallback=None))

    schedule_leagues = [
        config.getlist('SCHEDULE_LEAGUES', o)
        for o in config['SCHEDULE_LEAGUES'].keys()
    ]
    handler = {
        'calendar': (CalendarHandler, config.get('CALENDAR', 'id')),
        'table': table_handler,
        'schedule': (ScheduleHandler, schedule_leagues)
    }
    source_hdl = handler[source][0](*handler[source][1:])
    dest_hdl = handler[dest][0](*handler[dest][1:])

    if not (source_hdl.connect() and dest_hdl.connect()):
        raise RuntimeError('Connection to the target failed.')

    source_events = source_hdl.list_events().values()
    dest_events = dest_hdl.list_events()

    new_events = []
    update_events = {}
    delete_events = list(dest_events.keys())

    # determine which events to add, delete and update
    # if the source is the schedule, ignore leagues, that are not present in the leage definitions (to allow custom events)
    if isinstance(source_hdl, ScheduleHandler):
        leagues = [l[0] for l in schedule_leagues]

        for id in dest_events.keys():
            if dest_events[id].league not in leagues:
                delete_events.remove(id)

    for ev in source_events:
        for id in dest_events:
            if ev == dest_events[id]:
                if id in delete_events:
                    delete_events.remove(id)
                break
            elif ev.is_same(dest_events[id]):
                if id not in update_events:
                    update_events[id] = ev
                if id in delete_events:
                    delete_events.remove(id)
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
