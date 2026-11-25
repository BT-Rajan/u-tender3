import uuid

from sqlalchemy import DateTime as _SADateTime
from sqlalchemy.dialects import mysql


def gen_uuid() -> str:
    return str(uuid.uuid4())


# MySQL DATETIME keeps whole seconds unless told otherwise, so writes in the same second
# compare equal and ordering by time becomes ambiguous. Keep microseconds on every timestamp.
DateTime = _SADateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
