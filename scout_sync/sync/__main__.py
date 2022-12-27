from argparse import ArgumentParser
from .sync import sync, refresh_oauth_credentials, set_simulate

parser = ArgumentParser()
parser.add_argument('--from', dest='source',
                    choices=['calendar', 'table', 'schedule'])
parser.add_argument('--to', dest='dest',
                    choices=['calendar', 'table'])
parser.add_argument('--simulate', action='store_true')
parser.add_argument('--refresh-credentials', action='store_true')
ARGS = parser.parse_args()

set_simulate(ARGS.simulate)

if ARGS.refresh_credentials:
    credentials = refresh_oauth_credentials()
    print(credentials.to_json())
    
if ARGS.source and ARGS.dest:
    sync(ARGS.source, ARGS.dest)

if not ((ARGS.source and ARGS.dest) or ARGS.refresh_credentials):
    parser.print_usage()
