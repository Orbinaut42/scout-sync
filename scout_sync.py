import sys
import os
import logging
import locale
import requests
import datetime as dt
import ics
import json
from argparse import ArgumentParser
from configparser import ConfigParser
import googleapiclient.discovery
import google_auth_oauthlib
import google
import ezodf

os.chdir(os.path.dirname(os.path.realpath(__file__)))

_CONFIG = ConfigParser()
_CONFIG.optionxform = str
_CONFIG.read('scout_sync.cfg', encoding='utf8')

# read email adresses and OAuth credentials from environment variables for Replit compatibility
for name, email in json.loads(os.getenv('EMAILS', default='{}')).items():
    _CONFIG['EMAILS'][name] = email

_CONFIG['CALENDAR']['credentials'] = os.getenv('OAUTH_CREDENTIALS', default='')

logging.basicConfig(filename=_CONFIG.get('COMMON', 'log_file'),
                    format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%dT%H:%M:%S',
                    level=logging.INFO)
logging.getLogger("googleapiclient").setLevel(logging.ERROR)

def exception_logger(exc_type, exc_value, exc_traceback):
    logging.error(exc_type.__name__, exc_info=(exc_type, exc_value, exc_traceback))
    
sys.excepthook = exception_logger

locale.setlocale(locale.LC_TIME, '')


class _Event:    
    __emails = {k: v for k, v in _CONFIG.items('EMAILS')}
    __names = {v: k for k, v in _CONFIG.items('EMAILS')}

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
            date = dt.date.fromisoformat(row_vals['Datum'])
        except (TypeError, ValueError):
            date = None
            logging.warning("Invalid date in table: {}".format(row_vals['Datum']))

        try:
            s_time = dt.datetime.strptime(row_vals['Zeit'], 'PT%HH%MM%SS')
            time = dt.time(hour=s_time.hour, minute=s_time.minute)
        except (TypeError, ValueError) as err:
            time = dt.time()
            if isinstance(err, ValueError) and row_vals['Zeit']:
                logging.warning("Invalid time in table: {}".format(row_vals['Zeit']))
        
        e = cls()
        e.datetime = (dt.datetime.combine(date, time) if date else None)
        e.location = (row_vals['Halle'] or None)
        e.league = (row_vals['Liga'] or None)
        e.opponent = (row_vals['Gegner'] or None)
        e.scouter1 = (row_vals['Scouter1'] or None)
        e.scouter2 = (row_vals['Scouter2'] or None)
        e.scouter3 = (row_vals['Scouter3'] or None)
        e.has_scouters = True

        return e
    
    @classmethod
    def from_calendar_event(cls, event):
        if len(event['start']['dateTime']) == 25:
            event['start']['dateTime'] = event['start']['dateTime'][:-6]
        e = cls()
        e.datetime = dt.datetime.fromisoformat(event['start']['dateTime'])
        e.location = event.get('location', None)
        e.league = event.get('summary', None).replace('Scouting ', '')
        e.opponent = event.get('description', None)
        scouter_list = []
        for a in event.get('attendees', []):
            try:
                scouter_list.append(cls.__names[a['email']])
            except KeyError:
                logging.warning("Unknown email in calendar event at {0}: {1}".format(
                                    e.datetime, a['email']))

        e.scouter1 = (scouter_list[0] if len(scouter_list) > 0 else None)            
        e.scouter2 = (scouter_list[1] if len(scouter_list) > 1 else None)
        e.scouter3 = (scouter_list[2] if len(scouter_list) > 2 else None)
        e.has_scouters = True
        
        if not e.league:
            logging.warning("Calendar event at {} has no league".format(e.datetime))
        
        return e

    @classmethod
    def from_ics(cls, event, team):
        e = cls()
        e.datetime = event.begin.to(_CONFIG.get('COMMON', 'timezone')).naive
        location_code = event.name.split(',')[1].strip()
        e.location = _ScheduleHandler.arenas.get(location_code, location_code) or None
        e.league = team['league_name']
        e.opponent = event.name.replace(team['team_name'] + '-', '').split(',')[0].strip() or None
        e.scouter1 = None
        e.scouter2 = None
        e.scouter3 = None
        e.has_scouters = False

        if location_code and location_code not in _ScheduleHandler.arenas:
            logging.warning("Event at {0}: Unknown arena in Schedule: {1}".format(
                                e.datetime, location_code))
        
        return e

    def as_calendar_event(self):
        event = {}
        if self.datetime:
            event['start'] = {'dateTime': self.datetime.isoformat(),
                              'timeZone': _CalendarHandler.timezone}
            event['end'] = {'dateTime': (self.datetime + dt.timedelta(hours=2)).isoformat(),
                            'timeZone': _CalendarHandler.timezone}
        else:
            logging.warning("Can not create calendar event: event has no date")
            return None

        event['location'] = self.location
        event['summary'] = "Scouting " + self.league
        event['description'] = self.opponent

        event['attendees'] = []
        scouterlist = [self.scouter1, self.scouter2, self.scouter3]
        for scouter in [s for s in scouterlist if s and s.strip()]:
            try:
                event['attendees'].append({"email": self.__emails[scouter],
                                            "displayName": scouter})
            except KeyError:
                logging.warning("Unknown scouter name in event at {0}: {1}".format(
                                    self.datetime, scouter))

        event['reminders'] =  {'useDefault': False,
                               'overrides': [{'method': 'popup', 'minutes': 360}]}

        return event

    def as_ods_row(self, captions):
        atts = {'Datum': (self.datetime.date().isoformat(), 'date'),
                'Zeit': (self.datetime.strftime('PT%HH%MM%SS'), 'time'),
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

    def as_string(self):
        info_list = ((i or '') for i in (
                        (self.datetime.strftime('%a, %d.%b %y %H:%M') if self.datetime
                                                                      else None),
                        self.location, self.league, self.opponent, 
                        self.scouter1, self.scouter2, self.scouter3))
        return "{0}, {1}, {2}, {3}, {4}, {5}, {6}".format(*info_list)

    def is_same(self, event):
        self_date = (self.datetime.date() if self.datetime else None)
        event_date = (event.datetime.date() if event.datetime else None)
        return all([self.league == event.league,
                    self_date == event_date,
                    self.opponent == event.opponent])

    def __eq__(self, event):
        self_scouter_list = [self.scouter1, self.scouter2, self.scouter3]
        event_scouter_list = [event.scouter1, event.scouter2, event.scouter3]

        if not (self.has_scouters and event.has_scouters):
            self_scouter_list = event_scouter_list
        
        return all([self.league == event.league,
                    self.datetime == event.datetime,
                    self.opponent == event.opponent,
                    self.location == event.location,
                    all(s in self_scouter_list for s in event_scouter_list),
                    all(s in event_scouter_list for s in self_scouter_list)])


class _CalendarHandler:
    timezone = _CONFIG.get('COMMON', 'timezone')

    def __init__(self, id):
        self.__id = id
        self.__service = None

    def connect(self):
        cred_info = _CONFIG.get('CALENDAR', 'credentials')
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(json.loads(cred_info) if cred_info else None)

        if not credentials.valid and credentials.expired and credentials.refresh_token:
            credentials.refresh(google.auth.transport.requests.Request())

        self.__service = googleapiclient.discovery.build('calendar', 'v3', credentials=credentials, static_discovery=False)
        if self.__service:
            logging.info("Connected to calendar: {0}".format(self.__id))
            return True
        else: 
            logging.error("Connection to calendar with ID {0} failed".format(self.__id))
            return False

    def add_events(self, events, do_sim):
        if not self.__service:
            return

        for ev in events:
            cal_ev = ev.as_calendar_event()
            date = dt.datetime.fromisoformat(cal_ev['start']['dateTime'])
            now = dt.datetime.now()
            
            act = self.__service.events().insert(
                    calendarId=self.__id,
                    sendUpdates=('all' if date > now else 'none'),
                    body=cal_ev)
            if not do_sim:
                act.execute()
            
            logging.info("{1}Added event to calendar: {0}".format(
                            ev.as_string(), ("(SIMULATED) " if do_sim else '')))

    def update_events(self, events, do_sim):
        if not self.__service:
            return

        for id in events:
            cal_ev = _Event.from_calendar_event(
                        self.__service.events().get(calendarId=self.__id,
                                                    eventId=id).execute())
            new_ev = events[id]
            if not new_ev.has_scouters:
                new_ev.scouter1 = cal_ev.scouter1
                new_ev.scouter2 = cal_ev.scouter2
                new_ev.scouter3 = cal_ev.scouter3
                new_ev.has_scouters = True

            now = dt.datetime.now()
            act = self.__service.events().update(
                    calendarId=self.__id,
                    eventId=id,
                    sendUpdates=('all' if cal_ev.datetime > now
                                          or new_ev.datetime > now
                                       else 'none'),
                    body=new_ev.as_calendar_event())
            if not do_sim:
                act.execute()

            logging.info(("{2}Updated event in calendar: {0}\n" + 50*' ' + "=> {1}").format(
                            cal_ev.as_string(),
                            new_ev.as_string(),
                            ("(SIMULATED) " if do_sim else '')))

    def delete_events(self, ids, do_sim):
        if not self.__service:
            return
        
        for id in ids:
            ev = _Event.from_calendar_event(
                    self.__service.events().get(calendarId=self.__id, eventId=id).execute())
            now = dt.datetime.now()
            act = self.__service.events().delete(
                    calendarId=self.__id,
                    sendUpdates=('all' if ev.datetime > now else 'none'),
                    eventId=id)
            if not do_sim:
                act.execute()

            logging.info("{1}Deleted event in calendar: {0}".format(
                            ev.as_string(), ("(SIMULATED) " if do_sim else '')))

    def list_events(self):
        if not self.__service:
            return

        events = self.__service.events().list(
                    calendarId=self.__id,
                    singleEvents=True,
                    orderBy='startTime').execute()   
        ev_list = events.get('items', [])
        return {ev['id']: _Event.from_calendar_event(ev) for ev in ev_list}


class _TableHandler:
    __captions_row = _CONFIG.getint('TABLE', 'captions_row')

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
                self.__captions.extend([cell.value] if cell.value != "Scouter"
                                       else ["Scouter1", "Scouter2", "Scouter3"])
        
            while self.__captions and not self.__captions[-1]:
                del self.__captions[-1]

            for i, row in enumerate(self.__table.rows()):
                if i <= self.__captions_row or not any([cell.value for cell in row]):
                    continue
                   
                idx = max((self.__index.keys() or [-1])) + 1
                self.__index[idx] = row

            logging.info("Opened table: {0}".format(self.__file_name))
            return True
        else:
            logging.error("Can not open table: {0}".format(self.__file_name))
            return False

    def add_events(self, events, do_sim):
        table_events = sorted(self.list_events().values(),
                              key=lambda e: (e.datetime or dt.datetime.max))
        for ev in events:
            line = self.__captions_row + 1
            for te in table_events:
                if (te.datetime or dt.datetime.max) > (ev.datetime or dt.datetime.max):
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

            if not do_sim:
                self.__file.save()
            
            logging.info("{1}Added event to table: {0}".format(
                            ev.as_string(), ("(SIMULATED) " if do_sim else '')))

    def update_events(self, events, do_sim):
        for i in events:
            ev = _Event.from_table_row(self.__index[i], self.__captions)
            for c1, c2 in zip(self.__index[i], events[i].as_ods_row(self.__captions)):
                if c2 is None:
                    continue

                c1.set_value(c2.value, value_type=c2.value_type)
            
            if not do_sim:
                self.__file.save()

            new_ev = _Event.from_table_row(self.__index[i], self.__captions).as_string()
            logging.info(("{2}Updated event in table: {0}\n" + 47*' ' + "=> {1}").format(
                            ev.as_string(), new_ev, ("(SIMULATED) " if do_sim else '')))
        
    def delete_events(self, ids, do_sim):
        for idx in ids:
            ev = _Event.from_table_row(self.__index[idx], self.__captions)
            for i, row in enumerate(self.__table.rows()):
                if i <= self.__captions_row:
                    continue

                if ev == _Event.from_table_row(row, self.__captions):
                    self.__table.delete_rows(i)
                    if not do_sim:
                        self.__file.save()

                    logging.info("{1}Deleted event in table: {0}".format(
                                    ev.as_string(), ("(SIMULATED) " if do_sim else '')))
                    
                    break

    def list_events(self):    
        events = {}

        for i, row in self.__index.items():
            try:
                events[i] = _Event.from_table_row(row, self.__captions)
            except (TypeError, ValueError) as err:
                logging.warning("Can not create event: {}".format(err))     
        
        return events
    

class _ScheduleHandler:
    arenas = dict(_CONFIG['SCHEDULE_ARENAS'])

    def __init__(self, leagues):
        self.__schedules = {}
        self.__leagues = {l[2]:{'team_name': l[3],
                                'league_name': l[0],
                                'league_id': l[1]}
                          for l in leagues}

    def connect(self):
        for team_id in self.__leagues:
            url = 'https://www.basketball-bund.net/servlet/KalenderDienst'
            params = {'typ': 2,
                      'liga_id': self.__leagues[team_id]['league_id'],
                      'ms_liga_id': team_id,
                      'spt': '-1'}

            r = requests.get(url, params)
            if r.status_code == 200:
                try:
                    self.__schedules[team_id] = (self.__leagues[team_id],
                                                 ics.Calendar(r.text))
                except(KeyError):
                    logging.error('Can not read schedule for league {}'.format(
                                    self.__leagues[team_id]['league_name']))
                    return False
            else:
                logging.error('Can not download schedule for league {0} ({1}: {2})'.format(
                                self.__leagues[team_id]['league_name'],
                                r.status_code, r.reason))
                return False

        logging.info('Downloaded {} schedules'.format(len(self.__schedules)))
        return True

    def list_events(self):
        events = []
        for team, schedule in self.__schedules.values():
            url = 'https://www.basketball-bund.net/rest/competition/spielplan/id/' + team['league_id']
            r = requests.get(url)
            json_schedule = None
            if r.status_code == 200:
                try:
                    json_schedule = json.loads(r.text)
                except(json.decoder.JSONDecodeError):
                    logging.warning('Can not read JSON schedule for league {}'.format(
                                    team['league_name']))
            else:
                logging.warning('Can not download JSON schedule for league {0} ({1}: {2})'.format(
                                team['league_name'],
                                r.status_code, r.reason))
                
            for e in schedule.events:
                if e.name.startswith(team['team_name']):
                    if json_schedule:
                        for match in json_schedule['data']['matches']:
                            if str(match['matchId']) == e.uid:
                                cancelled = any([match['abgesagt'], match['verzicht']])
                                break
                    
                    if not cancelled:
                        events.append(_Event.from_ics(e, team))

        return {i: event for i, event in enumerate(events)}


def sync(source, dest, simulate=False):
    logging.info("Starting sync from {0} to {1}".format(source, dest))

    schedule_leagues = [tuple(v.strip() for v in l[1].split(','))
                            for l in _CONFIG.items('SCHEDULE_LEAGUES')]
    handler = {'calendar': (_CalendarHandler, _CONFIG.get('CALENDAR', 'id')),
               'table': (_TableHandler,
                         _CONFIG.get('TABLE', 'file'),
                         _CONFIG.get('TABLE', 'sheet')),
               'schedule': (_ScheduleHandler, schedule_leagues)}

    source_hdl = handler[source][0](*handler[source][1:])
    dest_hdl = handler[dest][0](*handler[dest][1:])
    
    if not (source_hdl.connect() and dest_hdl.connect()):
        return
    
    source_events = source_hdl.list_events().values()
    dest_events = dest_hdl.list_events()

    new_events = []
    update_events = {}
    delete_events = list(dest_events.keys())

    if isinstance(source_hdl, _ScheduleHandler):
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
            if ev.datetime or not isinstance(dest_hdl, _CalendarHandler):
                if ev not in new_events:
                    new_events.append(ev)

    dest_hdl.add_events(new_events, simulate)
    dest_hdl.update_events(update_events, simulate)
    dest_hdl.delete_events(delete_events, simulate)  

    logging.info("Sync finished")

def refresh_oauth_credentials():
    scopes = ['https://www.googleapis.com/auth/calendar.events']
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
    credentials = flow.run_local_server(port=0)

    _CONFIG['CALENDAR']['credentials'] = credentials.to_json()
    return credentials

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--from', dest='source',
                        choices=['calendar', 'table', 'schedule'])
    parser.add_argument('--to', dest='dest',
                        choices=['calendar', 'table'])
    parser.add_argument('--simulate', action='store_true')
    parser.add_argument('--refresh-credentials', action='store_true')
    ARGS = parser.parse_args()

    if ARGS.refresh_credentials:
        credentials = refresh_oauth_credentials()
        print(credentials.to_json())
        
    if ARGS.source and ARGS.dest:
        sync(ARGS.source, ARGS.dest, ARGS.simulate)

    if not ((ARGS.source and ARGS.dest) or ARGS.refresh_credentials):
        parser.print_usage()
