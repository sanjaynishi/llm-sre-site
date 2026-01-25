# sitecustomize.py
# Auto-imported by Python at startup (unless python is run with -S)

import sys

def _install_sqlite_shim():
    # Try both module names depending on which wheel is installed
    for mod in ("pysqlite3", "pysqlite3mc"):
        try:
            m = __import__(mod)
            sqlite3 = m.dbapi2
            sys.modules["sqlite3"] = sqlite3
            return True
        except Exception:
            continue
    return False

_install_sqlite_shim()