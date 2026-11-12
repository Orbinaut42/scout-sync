import logging

from . import update_schedule_leagues


logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
update_schedule_leagues()
