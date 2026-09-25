"""Database connection.

The target is a libpq connection string taken from ``TENDERWATCH_DSN``
(default: ``dbname=tenderwatch``, i.e. a local database over the unix socket).
"""
import os
from importlib import resources

import psycopg2
import psycopg2.extras


def connect():
    conn = psycopg2.connect(os.environ.get("TENDERWATCH_DSN", "dbname=tenderwatch"))
    psycopg2.extras.register_uuid()
    return conn


def init_schema(conn):
    """Create tables, function and views. Idempotent."""
    sql = resources.files("tenderwatch").joinpath("schema.sql").read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
