import os
import logging
import requests
import arrow
import json
import time
import google
import googleapiclient.discovery
import google_auth_oauthlib
import ezodf
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
    __emails = {k: v for k, v in config.items('EMAILS')}
    __names = {v: k for k, v in config.items('EMAILS')}

    def __init__(self, datetime=None, location=None, league=None,
                 opponent=None, scouter1=None, scouter2=None, scouter3=None):
        self.datetime = datetime
        self.location = location
        self.league = league
        self.opponent = opponent
        self.scouter1 = scouter1
        self.scouter2 = scouter2
        self.scouter3 = scouter3
        self.has_scouters = any([self.scouter1, self.scouter2, self.scouter3])

    @classmethod
    def from_table_row(cls, row, captions):
        row_vals = {cap: cell.value for cell, cap in zip(row, captions) if cap}
            
        try:
            date = arrow.get(row_vals['Datum'])
        except (TypeError, ValueError):
            date = None
            logging.warning(f"Invalid date in table: {row_vals['Datum']}")

        try:
            time = arrow.get(row_vals['Zeit'], '[PT]HH[H]mm[M]SS[S]')
        except (TypeError, ValueError) as err:
            time = arrow.get(0)
            if isinstance(err, ValueError) and row_vals['Zeit']:
                logging.warning(f"Invalid time in table: {row_vals['Zeit']}")
        
        e = cls()
        e.datetime = (
            date.replace(hour=time.hour, minute=time.minute, tzinfo=TIMEZONE) if date is not None
            else None)
        e.location = row_vals['Halle'] or None
        e.league = row_vals['Liga'] or None
        e.opponent = row_vals['Gegner'] or None
        e.scouter1 = row_vals['Scouter1'] or None
        e.scouter2 = row_vals['Scouter2'] or None
        e.scouter3 = row_vals['Scouter3'] or None
        e.has_scouters = True

        return e
    
    @classmethod
    def from_calendar_event(cls, event):
        e = cls()
        e.datetime = arrow.get(event['start']['dateTime'])
        e.location = event.get('location', None)
        e.league = event.get('summary', '').replace('Scouting ', '') or None
        e.opponent = event.get('description', None)
        scouter_list = []
        for a in event.get('attendees', []):
            try:
                scouter_list.append(cls.__names[a['email']])
            except KeyError:
                logging.warning(f"Unknown email in calendar event at {e.datetime}: {a['email']}")

        e.scouter1 = (scouter_list[0] if len(scouter_list) > 0 else None)            
        e.scouter2 = (scouter_list[1] if len(scouter_list) > 1 else None)
        e.scouter3 = (scouter_list[2] if len(scouter_list) > 2 else None)
        e.has_scouters = True
        
        if not e.league:
            logging.warning(f"Calendar event at {e.datetime} has no league")
        
        return e

    @classmethod
    def from_ics(cls, event, team):
        e = cls()
        e.datetime = arrow.get(event.begin.to(TIMEZONE))
        location_code = event.name.split(',')[1].strip()
        e.location = ScheduleHandler.arenas.get(location_code, location_code) or None
        e.league = team['league_name']
        e.opponent = event.name.replace(team['team_name'] + '-', '').split(',')[0].strip() or None
        e.scouter1 = None
        e.scouter2 = None
        e.scouter3 = None
        e.has_scouters = False

        if location_code and location_code not in ScheduleHandler.arenas:
            logging.warning(f"Event at {e.datetime}: Unknown arena in Schedule: {location_code}")
        
        return e
    
    @classmethod
    def from_JSON_schedule(cls, event, league_name):
        e = cls()
        e.datetime = arrow.get(f'{event["kickoffDate"]}T{event["kickoffTime"]}', tzinfo=TIMEZONE)
        location_id = str(event['matchInfo']['spielfeld']['id'])
        e.location = ScheduleHandler.arenas.get(
            location_id,
            event['matchInfo']['spielfeld']['bezeichnung'])
        e.league = league_name
        e.opponent = event['guestTeam']['teamname']
        e.scouter1 = None
        e.scouter2 = None
        e.scouter3 = None
        e.has_scouters = False

        if location_id and location_id not in ScheduleHandler.arenas:
            logging.warning(f"Event at {e.datetime}: Unknown arena ID in Schedule: {location_id}")
        
        return e

    def as_calendar_event(self):
        event = {}
        if self.datetime:
            event['start'] = {
                'dateTime': self.datetime.isoformat(),
                'timeZone': TIMEZONE}
            event['end'] = {
                'dateTime': self.datetime.shift(hours=2).isoformat(),
                'timeZone': TIMEZONE}
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
                event['attendees'].append(
                    {"email": self.__emails[scouter], "displayName": scouter})
            except KeyError:
                logging.warning(f"Unknown scouter name in event at {self.datetime}: {scouter}")

        event['reminders'] =  {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 360}]}

        return event

    def as_ods_row(self, captions):
        atts = {
            'Datum': (self.datetime.date().isoformat(), 'date'),
            'Zeit': (self.datetime.format('[PT]HH[H]mm[M]SS[S]'), 'time'),
            'Halle': (self.location, 'string'),
            'Liga': (self.league, 'string'),
            'Gegner': (self.opponent, 'string'),
            'Scouter1': (self.scouter1, 'string'),
            'Scouter2': (self.scouter2, 'string'),
            'Scouter3': (self.scouter3, 'string')}
    
        if atts['Zeit'][0] == 'PT00H00M00S':
            atts['Zeit'] = ('', 'string')

        default = {'', None}
        row = []
        for c in captions:
            val, tp = atts.get(c, default)

            if c.startswith('Scouter') and not self.has_scouters:
                row.append(None)
            else:                 
                row.append(ezodf.Cell((val or ''), value_type = tp))
            
        return row

    def __str__(self):
        info_list = ((i or '') for i in (
            self.datetime.format() if self.datetime else None,
            self.location, self.league, self.opponent, 
            self.scouter1, self.scouter2, self.scouter3))
        return '{0}, {1}, {2}, {3}, {4}, {5}, {6}'.format(*info_list)

    def is_same(self, event):
        self_date = self.datetime.date() if self.datetime else None
        event_date = event.datetime.date() if event.datetime else None
        return all([
            self.league == event.league,
            self_date == event_date,
            self.opponent == event.opponent])

    def __eq__(self, event):
        self_scouter_list = [self.scouter1, self.scouter2, self.scouter3]
        event_scouter_list = [event.scouter1, event.scouter2, event.scouter3]

        if not (self.has_scouters and event.has_scouters):
            self_scouter_list = event_scouter_list
        
        return all([
            self.league == event.league,
            self.datetime == event.datetime,
            self.opponent == event.opponent,
            self.location == event.location,
            all(s in self_scouter_list for s in event_scouter_list),
            all(s in event_scouter_list for s in self_scouter_list)])


class CalendarHandler:
    def __init__(self, calendar_id):
        self.__calendar_id = calendar_id
        self.__service = None

    def connect(self):
        def credentials_from_oauth_info(oauth_info):
            credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(
                json.loads(oauth_info) if oauth_info else None)
            if not credentials.valid and credentials.expired and credentials.refresh_token:
                credentials.refresh(google.auth.transport.requests.Request())
            return credentials
        
        def credentials_from_service_account_info(account_info):
            credentials = google.oauth2.service_account.Credentials.from_service_account_info(
                json.loads(account_info) if account_info else None)
            return credentials

        # prioritise authentication with service account
        auth_info = {
            'secrets_info': (
                credentials_from_oauth_info,
                config.get('CALENDAR', 'oauth_info')),
            'service_account_info': (
                credentials_from_service_account_info,
                config.get('CALENDAR', 'service_account_info'))}
        auth_method = (
            'service_account_info' if auth_info['service_account_info'][1]
            else 'secrets_info')
        credentials = auth_info[auth_method][0](auth_info[auth_method][1])
        self.__service = googleapiclient.discovery.build(
            'calendar', 'v3', credentials=credentials, static_discovery=False)

        if self.__service:
            logging.info(f"Connected to calendar: {self.__calendar_id}")
            return True
        else: 
            logging.error(f"Connection to calendar with ID {self.__calendar_id} failed")
            return False

    def add_events(self, events):
        if not self.__service:
            return

        for ev in events:
            cal_ev = ev.as_calendar_event()
            date = arrow.get(cal_ev['start']['dateTime'])
            now = arrow.now(TIMEZONE)
            
            act = self.__service.events().insert(
                    calendarId=self.__calendar_id,
                    sendUpdates=('all' if date > now else 'none'),
                    body=cal_ev)
            if not SIMULATE:
                act.execute()
            
            logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Added event to calendar:\n\t\t{ev}")

    def update_events(self, events):
        if not self.__service:
            return

        for id in events:
            cal_ev = Event.from_calendar_event(
                self.__service.events().get(calendarId=self.__calendar_id, eventId=id).execute())

            new_ev = events[id]
            if not new_ev.has_scouters:
                new_ev.scouter1 = cal_ev.scouter1
                new_ev.scouter2 = cal_ev.scouter2
                new_ev.scouter3 = cal_ev.scouter3
                new_ev.has_scouters = True

            now = arrow.now(TIMEZONE)
            act = self.__service.events().update(
                calendarId=self.__calendar_id,
                eventId=id,
                sendUpdates='all' if cal_ev.datetime > now or new_ev.datetime > now else 'none',
                body=new_ev.as_calendar_event())

            if not SIMULATE:
                act.execute()

            logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Updated event in calendar:\n\t-\t{cal_ev}\n\t+\t{new_ev}")

    def delete_events(self, ids):
        if not self.__service:
            return
        
        for id in ids:
            ev = Event.from_calendar_event(
                self.__service.events().get(calendarId=self.__calendar_id, eventId=id).execute())
            now = arrow.now(TIMEZONE)
            act = self.__service.events().delete(
                calendarId=self.__calendar_id,
                sendUpdates='all' if ev.datetime > now else 'none',
                eventId=id)

            if not SIMULATE:
                act.execute()

            logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Deleted event in calendar:\n\t\t{ev}")

    def list_events(self):
        if not self.__service:
            return

        events = self.__service.events().list(
            calendarId=self.__calendar_id,
            singleEvents=True,
            orderBy='startTime').execute()   
        ev_list = events.get('items', [])
        return {ev['id']: Event.from_calendar_event(ev) for ev in ev_list}


class TableHandler:
    __captions_row = int(config.getint('TABLE', 'captions_row', fallback=None) or 0)

    def __init__(self, file_name, sheet_name=None):
        self.__file_name = file_name
        self.__sheet_name = sheet_name
        self.__file = None
        self.__table = None
        self.__captions = []
        self.__index = {}

    def connect(self):
        self.__file = ezodf.opendoc(self.__file_name)

        if self.__file:
            self.__table = self.__file.sheets[(self.__sheet_name or 0)]
            
            for cell in self.__table.row(self.__captions_row):
                self.__captions.extend(
                    [cell.value] if cell.value != 'Scouter'
                    else ['Scouter1', 'Scouter2', 'Scouter3'])
        
            while self.__captions and not self.__captions[-1]:
                del self.__captions[-1]

            for i, row in enumerate(self.__table.rows()):
                if i <= self.__captions_row or not any([cell.value for cell in row]):
                    continue
                   
                idx = max((self.__index.keys() or [-1])) + 1
                self.__index[idx] = row

            logging.info(f"Opened table: {self.__file_name}")
            return True
        else:
            logging.error(f"Can not open table: {self.__file_name}")
            return False

    def add_events(self, events):
        table_events = sorted(
            self.list_events().values(),
            key=lambda e: (e.datetime or arrow.Arrow(9999)))

        for ev in events:
            line = self.__captions_row + 1

            for te in table_events:
                if (te.datetime or arrow.Arrow(9999)) > (ev.datetime or arrow.Arrow(9999)):
                    break

                line += 1

            self.__table.insert_rows(line)
            idx = max((self.__index.keys() or [-1])) + 1
            self.__index[idx] = self.__table.row(line)
            table_events.insert(line-self.__captions_row-1, ev)

            for c1, c2 in zip(self.__index[idx], ev.as_ods_row(self.__captions)):
                if c2 is None:
                    continue

                c1.set_value(c2.value, value_type=c2.value_type)

            if not SIMULATE:
                self.__file.save()
            
            logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Added event to table:\n\t\t{ev}")

    def update_events(self, events):
        for i in events:
            ev = Event.from_table_row(self.__index[i], self.__captions)
            for c1, c2 in zip(self.__index[i], events[i].as_ods_row(self.__captions)):
                if c2 is None:
                    continue

                c1.set_value(c2.value, value_type=c2.value_type)
            
            if not SIMULATE:
                self.__file.save()

            new_ev = Event.from_table_row(self.__index[i], self.__captions)
            logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Updated event in table:\n\t-\t{ev}\n\t+\t{new_ev}")
        
    def delete_events(self, ids):
        for idx in ids:
            ev = Event.from_table_row(self.__index[idx], self.__captions)
            for i, row in enumerate(self.__table.rows()):
                if i <= self.__captions_row:
                    continue

                if ev == Event.from_table_row(row, self.__captions):
                    self.__table.delete_rows(i)

                    if not SIMULATE:
                        self.__file.save()

                    logging.info(f"{'(SIMULATED) ' if SIMULATE else ''}Deleted event in table:\n\t\t{ev}")
                    
                    break

    def list_events(self):    
        events = {}

        for i, row in self.__index.items():
            try:
                events[i] = Event.from_table_row(row, self.__captions)
            except (TypeError, ValueError) as err:
                logging.warning(f"Can not create event: {err}")     
        
        return events
    

class ScheduleHandler:
    arenas = dict(config['SCHEDULE_ARENAS'])
    __REQUEST_TIMEOUT = 5

    def __init__(self, leagues):
        self.__schedule = []
        self.__leagues = [dict(zip(['league_name', 'league_id', 'team_id'], l)) for l in leagues]

    def connect(self):
        api_url = 'https://www.basketball-bund.net/rest'
        schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"
        match_info_url = f"{api_url}/match/id/{{match_id}}/matchInfo"
        self.__schedule = []

        with requests.Session() as s:
            for league in self.__leagues:
                # get the complete league schedule
                league_name, league_id, team_id = league.values()
                r = s.get(
                    schedule_url.format(league_id=league_id),
                    timeout=ScheduleHandler.__REQUEST_TIMEOUT)

                if r.status_code == 200:
                    try:
                        league_schedule = r.json()
                    except(json.decoder.JSONDecodeError):
                        logging.error(f"Can not read schedule for league {league_name}")
                        return False
                else:
                    logging.error(f"Can not download schedule for league {league_name} ({r.status_code}: {r.reason})")
                    return False

                team_matches = [
                    match['matchId']
                    for match in league_schedule['data']['matches']
                    if match['homeTeam']['teamPermanentId'] == team_id]

                # get the details for each match
                for match_id in team_matches:
                    r = s.get(
                        match_info_url.format(match_id=match_id),
                        timeout=ScheduleHandler.__REQUEST_TIMEOUT)

                    if r.status_code == 200:
                        try:
                            match_info = r.json()
                        except(json.decoder.JSONDecodeError):
                            logging.error(f"Can not read game details for game {match_id} for league {league_name}")
                            return False
                    else:
                        logging.error(f"Can not download game details for game {match_id} for league {league_name} ({r.status_code}: {r.reason})")
                        return False

                    self.__schedule.append((match_info['data'], league_name))

        logging.info(f"Downloaded {len(self.__schedule)} game schedules from {len(self.__leagues)} leagues")
        return True

    def list_events(self):
        events = []
        for match, league_name in self.__schedule:
            cancelled = any([match['abgesagt'], match['verzicht']]) 

            if not cancelled:
                events.append(Event.from_JSON_schedule(match, league_name))

        return {i: event for i, event in enumerate(events)}


def sync(source, dest):
    logging.info(f"Starting sync from {source} to {dest}")

    start_time = time.time()
    schedule_leagues = [
        config.getlist('SCHEDULE_LEAGUES', o)
        for o in config['SCHEDULE_LEAGUES'].keys()]
    handler = {
        'calendar': (CalendarHandler, config.get('CALENDAR', 'id')),
        'table': (TableHandler, config.get('TABLE', 'file'), config.get('TABLE', 'sheet', fallback = None)),
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
            if ev.datetime or not isinstance(dest_hdl, CalendarHandler):
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
    
def refresh_oauth_token():
    """refresh an expired installed app OAuth token"""
    secrets_file = 'secrets.json'

    secrets_path_file = os.path.join(os.path.dirname(__file__), secrets_file)
    scopes = ['https://www.googleapis.com/auth/calendar.events']
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        secrets_path_file, scopes)
    credentials = flow.run_local_server(port=0)

    return credentials
