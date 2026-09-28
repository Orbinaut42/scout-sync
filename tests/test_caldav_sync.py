import logging
import sys

import arrow
import icalendar
import pytest

from scout_sync.config import config
from scout_sync.sync.sync import TIMEZONE, CalDavHandler, Event

sync_module = sys.modules['scout_sync.sync.sync']


NAMES = {
    'Alice': 'alice@example.com',
    'Bob': 'bob@example.com'}
EMAILS = {email: name for name, email in NAMES.items()}


@pytest.fixture
def scouter_maps(monkeypatch):
    monkeypatch.setattr(Event, '_emails', NAMES.copy())
    monkeypatch.setattr(Event, '_names', EMAILS.copy())
    return NAMES


def future_event(**overrides):
    values = {
        'id': '55802_163079_12',
        'datetime': arrow.get(2030, 9, 20, 16, 30, tzinfo=TIMEZONE),
        'location': 'Arena',
        'league': 'BBL',
        'opponent': 'Opponent A',
        'scouters': ['Alice', 'Bob'],
        'schedule_info': {'match_id': 'match-1', 'league_id': 'league-1'}}
    values.update(overrides)
    return Event(**values)


def wrap_ical(component):
    calendar = icalendar.Calendar()
    calendar.add('prodid', '-//Scout Sync//')
    calendar.add('version', '2.0')
    calendar.add_component(component)
    return calendar


def attendees(vevent):
    value = vevent.get('attendee')
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class FakeCalDavEvent:
    def __init__(self, calendar_ical):
        self._ical = calendar_ical
        self.deleted = False
        self.save_calls = []

    def get_icalendar_component(self):
        return self._ical.walk('VEVENT')[0]

    @property
    def data(self):
        return self._ical

    @data.setter
    def data(self, value):
        if isinstance(value, icalendar.Calendar):
            self._ical = value
        else:
            self._ical = wrap_ical(value)

    def save(self, increase_seqno=True):
        self.save_calls.append({'increase_seqno': increase_seqno})
        return self

    def delete(self):
        self.deleted = True


class FakeCalendar:
    def __init__(self, name='Scouting', resources=None):
        self.name = name
        self._resources = list(resources or [])
        self.added = []

    def get_display_name(self):
        return self.name

    def get_events(self):
        return list(self._resources)

    def add_event(self, ical):
        if isinstance(ical, icalendar.Calendar):
            calendar_ical = ical
        else:
            calendar_ical = icalendar.Calendar.from_ical(ical)

        resource = FakeCalDavEvent(calendar_ical)
        self.added.append(resource)
        self._resources.append(resource)
        return resource


class FakePrincipal:
    def __init__(self, calendars):
        self._calendars = calendars

    def get_calendars(self):
        return self._calendars


class FakeClient:
    def __init__(self, calendars, scheduling=True):
        self._principal = FakePrincipal(calendars)
        self._scheduling = scheduling

    def get_calendars(self, principal=None):
        if principal is not None:
            return principal.get_calendars()
        else:
            return self.get_principal().get_calendars()

    def get_principal(self):
        return self._principal

    def supports_scheduling(self):
        return self._scheduling


def connected_handler(monkeypatch, resources=None, scheduling=True):
    calendar = FakeCalendar(resources=resources)
    client = FakeClient([calendar], scheduling=scheduling)
    monkeypatch.setattr(
        sync_module, 'get_davclient', lambda **kwargs: client)
    monkeypatch.setattr(
        type(config), 'caldav_url',
        property(lambda _: 'https://caldav.example.com'))
    monkeypatch.setattr(
        type(config), 'caldav_username',
        property(lambda _: 'scout@example.com'))
    monkeypatch.setattr(
        type(config), 'caldav_password',
        property(lambda _: 'secret'))

    handler = CalDavHandler('Scouting')
    assert handler.connect() is True
    return handler, calendar


def test_as_vevent_from_vevent_round_trip(scouter_maps):
    original = future_event()

    round_tripped = Event.from_vevent(original.as_vevent(sequence=3, notify=True))

    assert round_tripped.id == original.id
    assert round_tripped.datetime == original.datetime
    assert round_tripped.location == original.location
    assert round_tripped.league == original.league
    assert round_tripped.opponent == original.opponent
    assert sorted(round_tripped.scouters) == sorted(original.scouters)
    assert round_tripped.schedule_info == original.schedule_info


def test_from_vevent_requires_uid(scouter_maps):
    vevent = future_event().as_vevent()
    del vevent['uid']

    assert Event.from_vevent(vevent) is None


def test_as_vevent_omits_attendees_when_scouters_is_none(scouter_maps):
    vevent = future_event(scouters=None).as_vevent()

    assert vevent.get('attendee') is None


def test_as_vevent_empty_scouters_writes_no_attendees(scouter_maps):
    vevent = future_event(scouters=[]).as_vevent()

    assert vevent.get('attendee') is None


def test_as_vevent_notify_flag_sets_partstat_and_rsvp(scouter_maps):
    invited = future_event().as_vevent(notify=True)
    silent = future_event().as_vevent(notify=False)

    def parts(vevent):
        return {
            (str(a.params.get('CN')),
             str(a.params.get('PARTSTAT')).upper(),
             str(a.params.get('RSVP')).upper())
            for a in attendees(vevent)}

    assert parts(invited) == {
        ('Alice', 'NEEDS-ACTION', 'TRUE'),
        ('Bob', 'NEEDS-ACTION', 'TRUE')}
    assert parts(silent) == {
        ('Alice', 'ACCEPTED', 'FALSE'),
        ('Bob', 'ACCEPTED', 'FALSE')}


def test_as_vevent_writes_sequence(scouter_maps):
    vevent = future_event().as_vevent(sequence=4)

    assert int(vevent.get('sequence')) == 4


def test_as_vevent_sets_organizer_from_caldav_username(scouter_maps, monkeypatch):
    monkeypatch.setattr(
        type(config), 'caldav_username',
        property(lambda _: 'scout@example.com'))

    vevent = future_event().as_vevent()

    assert str(vevent.get('organizer')) == 'mailto:scout@example.com'


def test_from_vevent_skips_declined_attendees(scouter_maps):
    vevent = future_event(scouters=['Alice']).as_vevent()
    attendees(vevent)[0].params['partstat'] = 'DECLINED'

    event = Event.from_vevent(vevent)

    assert event.scouters == []


def test_from_vevent_handles_single_attendee(scouter_maps):
    vevent = future_event(scouters=['Bob']).as_vevent()

    event = Event.from_vevent(vevent)

    assert event.scouters == ['Bob']


def test_connect_fails_without_url(scouter_maps, monkeypatch, caplog):
    monkeypatch.setattr(
        type(config), 'caldav_url', property(lambda _: ''))
    handler = CalDavHandler('Scouting')

    with caplog.at_level(logging.ERROR):
        assert handler.connect() is False

    assert 'Connection to CalDAV calendar Scouting failed' in caplog.text


def test_connect_fails_for_unknown_calendar(scouter_maps, monkeypatch, caplog):
    client = FakeClient([FakeCalendar(name='Other')])
    monkeypatch.setattr(
        sync_module, 'get_davclient', lambda **kwargs: client)
    monkeypatch.setattr(
        type(config), 'caldav_url',
        property(lambda _: 'https://caldav.example.com'))
    handler = CalDavHandler('Scouting')

    with caplog.at_level(logging.ERROR):
        assert handler.connect() is False

    assert 'not found' in caplog.text


def test_connect_success_logs(scouter_maps, monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        handler, _ = connected_handler(monkeypatch)

    assert 'Connected to calendar: Scouting' in caplog.text


def test_list_events_when_disconnected_returns_none(scouter_maps):
    handler = CalDavHandler('Scouting')

    assert handler.list_events() is None


def test_mutators_when_disconnected_are_noops(scouter_maps):
    handler = CalDavHandler('Scouting')

    handler.add_events([future_event()])
    handler.update_events([future_event()])
    handler.delete_events([future_event()])


def test_list_events_builds_ids_and_skips_missing_uid(scouter_maps, monkeypatch):
    valid = FakeCalDavEvent(wrap_ical(future_event().as_vevent()))
    vevent = future_event(id='ignored').as_vevent()
    del vevent['uid']
    invalid = FakeCalDavEvent(wrap_ical(vevent))

    handler, _ = connected_handler(monkeypatch, resources=[valid, invalid])
    events = handler.list_events()

    assert [e.id for e in events] == ['55802_163079_12']
    assert list(handler._ids) == ['55802_163079_12']


def test_add_events_skips_missing_datetime_and_saves(scouter_maps, monkeypatch):
    handler, calendar = connected_handler(monkeypatch)
    handler.list_events()

    handler.add_events([
        future_event(id='manual-no-date', datetime=None),
        future_event(id='new-1')])

    assert len(calendar.added) == 1
    vevent = calendar.added[0].get_icalendar_component()
    assert str(vevent.get('uid')) == 'new-1'
    assert 'new-1' in handler._ids


def test_add_events_simulate_does_not_save(scouter_maps, monkeypatch):
    monkeypatch.setattr(sync_module, 'SIMULATE', True)
    handler, calendar = connected_handler(monkeypatch)
    handler.list_events()

    handler.add_events([future_event(id='new-1')])

    assert calendar.added == []


def test_update_events_increments_sequence(scouter_maps, monkeypatch):
    existing = FakeCalDavEvent(wrap_ical(future_event().as_vevent(sequence=2)))
    handler, _ = connected_handler(monkeypatch, resources=[existing])
    handler.list_events()

    handler.update_events([future_event(league='ProA')])

    assert existing.save_calls == [{'increase_seqno': False}]
    vevent = existing.get_icalendar_component()
    assert int(vevent.get('sequence')) == 3
    assert str(vevent.get('summary')) == 'Scouting ProA'


def test_update_events_missing_id_raises(scouter_maps, monkeypatch):
    handler, _ = connected_handler(monkeypatch)
    handler.list_events()

    with pytest.raises(ValueError, match='not in calendar'):
        handler.update_events([future_event(id='missing')])


def test_delete_events(scouter_maps, monkeypatch):
    existing = FakeCalDavEvent(wrap_ical(future_event().as_vevent()))
    handler, _ = connected_handler(monkeypatch, resources=[existing])
    handler.list_events()

    handler.delete_events([future_event()])

    assert existing.deleted is True


def test_delete_events_missing_id_raises(scouter_maps, monkeypatch):
    handler, _ = connected_handler(monkeypatch)
    handler.list_events()

    with pytest.raises(ValueError, match='not in calendar'):
        handler.delete_events([future_event(id='missing')])


def test_should_notify_only_future(scouter_maps):
    future = arrow.get(2030, 1, 1, tzinfo=TIMEZONE)
    past = arrow.get(2020, 1, 1, tzinfo=TIMEZONE)

    assert CalDavHandler._should_notify(future) is True
    assert CalDavHandler._should_notify(past) is False
    assert CalDavHandler._should_notify(past, future) is True
    assert CalDavHandler._should_notify(None, past) is False


def test_calendar_backend_property_values():
    from configparser import ConfigParser

    def backend_value(value=None):
        parser = ConfigParser()
        parser.add_section('COMMON')
        if value is not None:
            parser['COMMON']['calendar_backend'] = value

        class FakeConfig:
            _config_parser = parser

        return type(config).calendar_backend.fget(FakeConfig())

    assert backend_value('google') == 'google'
    assert backend_value('caldav') == 'caldav'
    assert backend_value(' CalDAV ') == 'caldav'
    assert backend_value() == 'caldav'

    with pytest.raises(ValueError, match='calendar_backend'):
        backend_value('outlook')
