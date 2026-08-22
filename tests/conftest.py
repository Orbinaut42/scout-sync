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
    original_scheduler = app_module._scheduler
    names = {
        'Alice': 'alice@example.com',
        'Bob': 'bob@example.com'}
    cache_file = tmp_path / 'web-cache.json'
    scheduler = FakeScheduler()

    monkeypatch.setattr(
        type(config), 'emails', property(lambda _: names.copy()))
    monkeypatch.setattr(
        type(config), 'web_cache_file', property(lambda _: str(cache_file)))
    monkeypatch.setattr(
        type(config), 'submit_pw', property(lambda _: 'secret'))
    monkeypatch.setattr(Event, '_emails', names.copy())
    monkeypatch.setattr(
        Event,
        '_names',
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
        app_module._scheduler = original_scheduler


def write_cache(cache_file, events):
    cache_file.write_text(
        json.dumps(events, ensure_ascii=False),
        encoding='utf8')
