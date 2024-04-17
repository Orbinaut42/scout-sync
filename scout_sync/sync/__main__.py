from argparse import ArgumentParser
from .sync import sync
from .google_api import refresh_oauth_token

parser = ArgumentParser()
parser.add_argument('--from', dest='source',
                    choices=['cache', 'schedule'])
parser.add_argument('--refresh-credentials', action='store_true')

ARGS = parser.parse_args()

if ARGS.refresh_credentials:
    credentials = refresh_oauth_token()
    print(credentials.to_json())
    
if ARGS.source:
    sync(ARGS.source)

if not (ARGS.source or ARGS.refresh_credentials):
    parser.print_usage()
