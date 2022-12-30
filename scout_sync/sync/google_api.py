import os
import json
import google
import googleapiclient.discovery
import google_auth_oauthlib
import arrow
from ..config import config

class GoogleAPI:
    def __init__(self, resource_id, timezone, simulate):
        self.__resource_id = resource_id
        self.__service = None
        self.__timezone = timezone
        self.__simulate = simulate

    @classmethod
    def __create_service(self, api_name, api_version):
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

        oauth_info = config.get('GOOGLE_API', 'oauth_info', fallback=None)
        service_account_info = config.get('GOOGLE_API', 'service_account_info', fallback=None)

        # prioritise authentication with service account
        if service_account_info:
            credentials = credentials_from_service_account_info(service_account_info)
        elif oauth_info:
            credentials = credentials_from_oauth_info(oauth_info)
        else:
            return
        
        self.__service = googleapiclient.discovery.build(
            api_name, api_version, credentials=credentials, static_discovery=False)

class GoogleCalendarAPI(GoogleAPI):
    def __init__(self, calendar_id, timezone, simulate=False):
        super.__init__(calendar_id,  timezone, simulate)

    def __connect_to_service(self):
        GoogleAPI.__create_service('calendar', 'v3')

        # test the connection
        self.__service.calendars().get(self.__resource_id).execute()
    
    def __get_all_events(self):
        events = self.__service.events().list(
            calendarId=self.__calendar_id,
            singleEvents=True,
            orderBy='startTime').execute()  

        return events.get('items', [])
    
    def __get_single_event(self, id):
        event = self.__service.events().get(
            calendarId=self.__resource_id,
            eventId=id).execute()

        return event
    
    def __insert_event(self, event):
            date = arrow.get(event['start']['dateTime'])
            now = arrow.now(self.__timezone)
            act = self.__service.events().insert(
                calendarId=self.__resource_id,
                body=event,
                sendUpdates=('all' if date > now else 'none'))

            if not self.__simulate:
                act.execute()
    
    def __update_event(self, id, old_event, new_event):
        old_date = arrow.get(old_event['start']['dateTime'])
        new_date = arrow.get(new_event['start']['dateTime'])
        now = arrow.now(self.__timezone)
        act = self.__service.events().update(
            calendarId=self.__resource_id,
            eventId=id,
            body=new_event,
            sendUpdates='all' if old_date > now or new_date > now else 'none')
        
        if not self.__simulate:
            act.execute()
    
    def __delete_event(self, id, event):
        date = arrow.get(event['start']['dateTime'])
        now = arrow.now(self.__timezone)
        act = self.__service.events().delete(
            calendarId=self.__resource_id,
            eventId=id,
            sendUpdates='all' if date > now else 'none')

        if not self.__simulate:
            act.execute()

class GoogleSheetsAPI(GoogleAPI):
    def __init__(self, spreadsheet_id, sheet_name, sheet_id, timezone, simulate=False):
        super.__init__(spreadsheet_id, timezone, simulate)
        self.__sheet_name = sheet_name
        self.__sheet_id = sheet_id

    @classmethod
    def serial_to_datetime(cls, serial, timezone):
        return arrow.get('1899-12-30', tzinfo=timezone).shift(days=serial)

    @classmethod
    def datetime_to_serial(cls, datetime):
        return (datetime - arrow.get('1899-12-30')).total_seconds() / (60 * 60 * 24)
    
    @classmethod
    def insert_row_request(cls, row, sheet_id):
        return {
            'insertDimension': {
                'inheritFromBefore': True,
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': row-1,
                    'endIndex': row
                },
            }
        }

    @classmethod
    def update_row_request(cls, row, data, sheet_id):
        return {
            'updateCells': {
                'start': {
                    'sheetId': sheet_id,
                    'rowIndex': row-1
                },
                'rows': [
                    {
                        'values': [
                            {
                                'userEnteredValue': {
                                    'numberValue' if isinstance(v, (int, float))
                                    else 'stringValue': v
                                }
                            } for v in data
                        ]
                    }
                ],
                'fields': 'userEnteredValue'
            }
        }
    
    @classmethod
    def delete_row_request(cls, row, sheet_id):
        return {
            'deleteDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': row-1,
                    'endIndex': row
                }
            }
        }

    def __batch_update(self, requests):
        body = {'requests': requests}
        act = self.__service.spreadsheets().batchUpdate(
            spreadsheetId=self.__resource_id,
            body=body)

        if not self.__simulate:
            act.execute()
    
    def __range_descriptor(self, start, end=None):
        if end is None:
            end = start
        
        sheet_descriptor = f"{self.__sheet_name}!" if self.__sheet_name is not None else ''
        if isinstance(start, tuple):
            return f"{sheet_descriptor}{start[0]}C{start[1]}:R{end[0]}C{end[1]}"
        else:
            return f"{sheet_descriptor}{start}:{end}"

    def __connect_to_service(self):
        GoogleAPI.__create_service('sheets', 'v4')

        # test the connection
        self.__service.spreadsheets().get(self.__resource_id).execute()
    
    def __get_range(self, range_start, range_end=None, major_dimension='ROWS', dims=0):
        values = self.__service.spreadsheets().values().get(
            spreadsheetId=self.__resource_id,
            range=self.__range_descriptor(range_start, range_end),
            valueRenderOption='UNFORMATTED_VALUE',
            majorDimension=major_dimension).execute()['values']
    	
        if dims==0:
            return values[0][0]
        elif dims==1:
            return values[0]
        else:
            return values

    def __insert_rows(self, rows_data):
        requests = []
        for row, data in sorted(rows_data, key=lambda r: r[0], reverse=True):
            requests.extend([
                GoogleSheetsAPI.insert_row_request(row, self.__sheet_id),
                GoogleSheetsAPI.update_row_request(row, data, self.__sheet_id)])
        
        self.__batch_update(requests)
    
    def __update_rows(self, rows_data):
        requests = [
            GoogleSheetsAPI.update_row_request(row, data, self.__sheet_id)
            for row, data in rows_data]
        self.__batch_update(requests)
    
    def __delete_rows(self, rows):
        requests = [
            GoogleSheetsAPI.delete_row_request(row, self.__sheet_id)
            for row in sorted(rows, reverse=True)]
        self.__batch_update(requests)

def refresh_oauth_token():
    """refresh an expired installed app OAuth token"""
    secrets_file = 'secrets.json'

    secrets_path_file = os.path.join(os.path.dirname(__file__), secrets_file)
    scopes = [
        'https://www.googleapis.com/auth/calendar.events',
        'https://www.googleapis.com/auth/spreadsheets']
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        secrets_path_file, scopes)
    credentials = flow.run_local_server(port=0)

    return credentials
