from endpoint.commands import initialize_commands
from endpoint.commit_log import initialize_commit_log
from endpoint.local_wiring import initialize_wiring
from endpoint.store import open_store, write_transaction


def initialize_endpoint(db):
    initialize_commands(db)
    initialize_wiring(db)
    initialize_commit_log(db)


def reopen_endpoint(path):
    db = open_store(path)
    try:
        with write_transaction(db):
            initialize_endpoint(db)
    except BaseException:
        db.close()
        raise
    return db
