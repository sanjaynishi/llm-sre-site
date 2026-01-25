# sitecustomize.py
import sys

try:
    import pysqlite3.dbapi2 as sqlite3  # type: ignore
    sys.modules["sqlite3"] = sqlite3
except Exception:
    pass