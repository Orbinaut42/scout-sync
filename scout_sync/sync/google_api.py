import os
import json
import google
import googleapiclient.discovery
import google_auth_oauthlib
import arrow
from ..config import config

class _GoogleAPI:
    """Base class for the Google API functionality"""

    def __init__(self, resource_id, timezone, simulate):
        """resource_id -> string Id of the calendar, spreadsheet, ...
        timezone -> string timezone for calendar event creation
        simulate -> bool whether the syncronisations should only be simulated (for testing purposes)"""
        self._resource_id = resource_id
        self._service = None
        self.__timezone = timezone
        self.__simulate = simulate

    def create_service(self, api_name, api_version):
        """Creates the Google API service ressource
        api_name -> string
        api_version -> string"""

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

        # prioritise authentication with oauth
        if oauth_info:
            credentials = credentials_from_oauth_info(oauth_info)
        elif service_account_info:
            credentials = credentials_from_service_account_info(service_account_info)
        else:
            raise ValueError(f'No authentication information provided for Google API "{api_name}"')
        
        self._service = googleapiclient.discovery.build(
            api_name, api_version, credentials=credentials, static_discovery=False)


class GoogleCalendarAPI(_GoogleAPI):
    """Convenience class for Google Calendar API functionalities"""

    def __init__(self, calendar_id, timezone, simulate=False):
        super().__init__(calendar_id,  timezone, simulate)

    def _connect_to_service(self):
        """Creates the service and tests the connection"""

        self.create_service('calendar', 'v3')

        # test the connection
        self._service.events().list(calendarId=self._resource_id).execute()
    
    def _get_all_events(self):
        """Returns al list of all events in the calendar"""

        events = self._service.events().list(
            calendarId=self._resource_id,
            singleEvents=True,
            orderBy='startTime').execute()  

        return events.get('items', [])
    
    def _get_single_event(self, id):
        """Returns the specified event"""

        event = self._service.events().get(
            calendarId=self._resource_id,
            eventId=id).execute()

        return event
    
    def _insert_event(self, event):
        """Inserts the event into the calendar
        the event should be passed as a dict"""

        date = arrow.get(event['start']['dateTime'])
        now = arrow.now(self._GoogleAPI__timezone)
        act = self._service.events().insert(
            calendarId=self._resource_id,
            body=event,
            sendUpdates=('all' if date > now else 'none'))

        if not self._GoogleAPI__simulate:
            act.execute()

    def _update_event(self, id, old_event, new_event):
        """Updates the event with the specified ID
        the events should be passed as a dicts"""

        old_date = arrow.get(old_event['start']['dateTime'])
        new_date = arrow.get(new_event['start']['dateTime'])
        now = arrow.now(self._GoogleAPI__timezone)
        act = self._service.events().update(
            calendarId=self._resource_id,
            eventId=id,
            body=new_event,
            sendUpdates='all' if old_date > now or new_date > now else 'none')
        
        if not self._GoogleAPI__simulate:
            act.execute()
    
    def _delete_event(self, id, event):
        """Deletes the specified event"""

        date = arrow.get(event['start']['dateTime'])
        now = arrow.now(self._GoogleAPI__timezone)
        act = self._service.events().delete(
            calendarId=self._resource_id,
            eventId=id,
            sendUpdates='all' if date > now else 'none')

        if not self._GoogleAPI__simulate:
            act.execute()


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
