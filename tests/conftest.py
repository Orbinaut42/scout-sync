import json

import pytest

import scout_sync.app.app as app_module
from scout_sync.config import config
from scout_sync.sync.sync import Event


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    original_emails = dict(config.items('EMAILS'))
    original_cache_file = config.get('COMMON', 'web_cache_file')
    original_submit_password = config.get('COMMON', 'submit_pw')
    original_scheduler = app_module._scheduler
    names = {
        'Alice': 'alice@example.com',
        'Bob': 'bob@example.com'}
    cache_file = tmp_path / 'web-cache.json'
    scheduler = FakeScheduler()

    config['EMAILS'].clear()
    config['EMAILS'].update(names)
    config.set('COMMON', 'web_cache_file', str(cache_file))
    config.set('COMMON', 'submit_pw', 'secret')
    monkeypatch.setattr(Event, '_Event__emails', names.copy())
    monkeypatch.setattr(
        Event,
        '_Event__names',
        {email: name for name, email in names.items()})
    monkeypatch.setattr(app_module, '_scheduler', scheduler)
    monkeypatch.setitem(app_module._app.config, 'TESTING', True)

    try:
        yield {
            'cache_file': cache_file,
            'client': app_module._app.test_client(),
            'names': names,
            'scheduler': scheduler}
    finally:
        config['EMAILS'].clear()
        config['EMAILS'].update(original_emails)
        config.set('COMMON', 'web_cache_file', original_cache_file)
        config.set('COMMON', 'submit_pw', original_submit_password)
        app_module._scheduler = original_scheduler


def write_cache(cache_file, events):
    cache_file.write_text(
        json.dumps(events, ensure_ascii=False),
        encoding='utf8')
