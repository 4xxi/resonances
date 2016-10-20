import logging
import math
from typing import List

from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.s3.bucket import Bucket
import sys

from sqlalchemy import Table
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Query
from sqlalchemy.orm.util import AliasedClass


def logging_done():
    logging.info('[done]')


def is_s3(path) -> bool:
    return 's3://' == path[:5]


def is_tar(path) -> bool:
    return path[-4:] == '.tar' or path[-7:] == '.tar.gz'


def cutoff_angle(value: float) -> float:
    """Cutoff input angle to interval from 0 to Pi or from 0 to -Pi
    if input angle is negative.

    :param float value:
    :rtype: float
    :return: angle in interval [0; Pi] or (0; -Pi]
    """
    if value > math.pi:
        while value > math.pi:
            value -= 2 * math.pi
    else:
        while value < -math.pi:
            value += 2 * math.pi
    return value


def get_asteroid_interval(from_line: str):
    starts_from = from_line.index('aei-') + 4
    ends_by = from_line.index('-', starts_from)
    start_asteroid_number = int(from_line[starts_from: ends_by])

    starts_from = ends_by + 1
    ends_by = from_line.index('.tar', starts_from)
    stop_asteroid_number = int(from_line[starts_from:ends_by])
    return start_asteroid_number, stop_asteroid_number


def create_aws_s3_key(access_key: str, secret_key: str, in_bucket: str, for_path: str) -> Key:
    conn = S3Connection(access_key, secret_key)
    bucket = conn.get_bucket(in_bucket)  # type: Bucket
    start = for_path.index(in_bucket)
    s3_filekey = for_path[start + len(in_bucket) + 1:]
    s3_bucket_key = bucket.new_key(s3_filekey)  # type: Key
    return s3_bucket_key


class ProgressBar:
    def __init__(self, width, title='', divider=2):
        self._divider = divider
        toolbar_width = width // divider
        sys.stdout.write("%s [%s]" % (title, " " * toolbar_width))
        sys.stdout.flush()
        sys.stdout.write("\b" * (toolbar_width + 1))
        self._counter = 0

    def update(self):
        self._counter += 1
        if self._counter % self._divider == 0:
            sys.stdout.write("#")
            sys.stdout.flush()

    def fin(self):
        sys.stdout.write("\n")
        self._counter = 0

    def __del__(self):
        self.fin()


def add_integer_filter(query: Query, ints: List[str], body_tables: List[AliasedClass]) -> Query:
    any_int = '*'

    for integer, table in zip(ints, body_tables):
        if integer != any_int:
            query = query.filter(eval("table.longitude_coeff %s" % integer))
    return query


def fix_id_sequence(for_table: Table, by_conn: Connection):
    by_conn.execute(('SELECT setval(\'%s_id_seq\', ' % for_table.name) +
                    'COALESCE((SELECT MAX(id)+1 FROM %s), 1), false);' % for_table.name)


