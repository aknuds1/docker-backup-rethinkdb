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
cl_parser.add_argument(
    '--tls_ca', default=None, help='RethinkDB CA certificate path'
)
args = cl_parser.parse_args()


logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
_logger = logging.getLogger()


def _prune_old(bucket):
    """Prune old backups."""
    def get_key(blob):
        return blob.updated

    _logger.info('Pruning old backups...')
    # Keep a certain amount of newest backups
    limit = 100
    sorted_blobs = sorted(
        bucket.list_blobs(prefix='rethinkdb/'), key=get_key, reverse=True
    )
    prunable_blobs = sorted_blobs[100:]
    for blob in prunable_blobs:
        _logger.debug(
            'Deleting blob {}, since we\'ve got more than {} backups'.format(
                blob.path, limit)
        )
        blob.delete()


def _do_backup():
    """Perform backup."""
    _logger.info('Backing up...')
    password = os.environ.get('BACKUP_PASSWORD')
    cmd = [
        'rethinkdb', 'dump', '-q', '-c', args.host, '-f', args.file,
        '--overwrite-file',
    ]
    if args.tls_ca:
        cmd.extend(['--tls-cert', args.tls_ca, ])
    if password:
        password_fpath = '/tmp/rethinkdb-password.txt'
        with open(password_fpath, 'wt') as f:
            f.write(password)
        cmd.extend(['--password-file', password_fpath, ])
    else:
        password_fpath = None
    try:
        subprocess.check_call(cmd)
    finally:
        if password_fpath:
            os.remove(password_fpath)

    credentials = service_account.Credentials.from_service_account_file(
        '/etc/rethinkdb-backup/key.json'
    )
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
