import sqlite3
from contextlib import contextmanager


def open_store(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


@contextmanager
def _transaction(db, begin):
    db.execute(begin)
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def read_transaction(db):
    return _transaction(db, 'BEGIN')


def write_transaction(db):
    return _transaction(db, 'BEGIN IMMEDIATE')
