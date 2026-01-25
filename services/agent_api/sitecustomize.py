import sys

try:
    import pysqlite3.dbapi2 as _sqlite3  # works for pysqlite3-binary
    sys.modules["sqlite3"] = _sqlite3
except Exception:
    try:
        import pysqlite3mc.dbapi2 as _sqlite3  # if you ever switch packages that expose pysqlite3mc
        sys.modules["sqlite3"] = _sqlite3
    except Exception:
        pass