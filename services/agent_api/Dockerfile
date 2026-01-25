FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# 1) Copy requirements first for better layer caching
COPY requirements.txt .

# 2) Install deps
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

# 3) Copy shim + app
COPY sitecustomize.py .
COPY app.py .

# 4) Build-time sanity check: enforce shim + verify chromadb import
RUN python - <<'PY'
import sys

# Try both possible module names for the sqlite wheel
sqlite3 = None
for mod in ("pysqlite3", "pysqlite3mc"):
    try:
        m = __import__(mod)
        sqlite3 = m.dbapi2
        break
    except Exception:
        pass

if sqlite3 is None:
    raise RuntimeError("Neither pysqlite3 nor pysqlite3mc is importable. Check requirements.txt wheel.")

sys.modules["sqlite3"] = sqlite3

import sqlite3 as s
print("sqlite_version:", s.sqlite_version)

import chromadb
print("chromadb_import: OK")
PY

CMD ["app.lambda_handler"]