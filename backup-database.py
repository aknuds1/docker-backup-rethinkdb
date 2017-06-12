#!/usr/bin/env python3
"""Back up RethinkDB and upload to Google Cloud Storage periodically."""
import asyncio
import sys
import contextlib
import logging
import subprocess
import os.path
from datetime import datetime, timezone
import argparse
import daemon
from google.oauth2 import service_account
from google.cloud import storage


_root_dir = os.path.abspath(os.path.dirname(__file__))
os.chdir(_root_dir)

cl_parser = argparse.ArgumentParser(description='Back up RethinkDB')
cl_parser.add_argument('--host', help='Database host', default='localhost')
cl_parser.add_argument(
    '--file', help='Backup archive path', default='/tmp/rethinkdb-dump.tar.gz')
cl_parser.add_argument(
    '--bucket', help='Google Cloud Storage bucket name')
cl_parser.add_argument(
    '--project_id', help='Google Cloud project ID')
args = cl_parser.parse_args()


logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
_logger = logging.getLogger()


def _prune_old(bucket):
    """Prune old backups."""
    _logger.info('Pruning old backups...')
    now = datetime.now(timezone.utc)
    for blob in bucket.list_blobs(prefix='rethinkdb/'):
        time_diff = now - blob.updated.replace(tzinfo=timezone.utc)
        if time_diff.days > 30:
            _logger.debug(
                'Deleting blob {}, since it\'s more than 30 days old'.format(
                    blob.path)
            )
            blob.delete()
        else:
            _logger.debug(
                'Not deleting blob {}, since it\'s only {} day(s) old'.format(
                    blob.path, time_diff.days)
            )


def _do_backup():
    """Perform backup."""
    _logger.info('Backing up...')
    subprocess.check_call([
        'rethinkdb', 'dump', '-q', '-c', args.host, '-f', args.file,
        '--overwrite-file',
    ])

    credentials = service_account.Credentials.from_service_account_info({
        'client_email': os.environ['BACKUP_CLIENT_EMAIL'],
        'private_key_id': os.environ['BACKUP_PRIVATE_KEY_ID'],
        'private_key': os.environ['BACKUP_PRIVATE_KEY'],
        'token_uri': 'https://accounts.google.com/o/oauth2/token',
    })
    client = storage.Client(
        project=args.project_id, credentials=credentials
    )
    date_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    storage_filename = 'rethinkdb/rethinkdb-dump-{}.tar.gz'.format(date_str)
    _logger.info(
        'Uploading archive to Cloud Storage: \'{}\'...'.format(
            storage_filename))
    bucket = client.get_bucket(args.bucket)
    blob = bucket.blob(storage_filename)
    blob.upload_from_filename(args.file)
    _logger.info('Successfully uploaded archive!')

    _prune_old(bucket)

    delay = 60 * 60 * 24
    _logger.info(
        'Scheduling next backup in {} hours...'.format(int(delay / (60 * 60))))
    loop.call_later(delay, _do_backup)


with daemon.DaemonContext(
    detach_process=False, stdout=sys.stdout, stderr=sys.stderr,
    working_directory=_root_dir
):
    with contextlib.closing(asyncio.get_event_loop()) as loop:
        _do_backup()
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            sys.exit(0)
