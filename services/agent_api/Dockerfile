FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# 1) Requirements first
COPY requirements.txt .

# 2) Install deps
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

# 3) Install sqlite shim globally so Python auto-imports it at startup
#    (this guarantees it runs BEFORE chromadb imports sqlite3)
COPY sitecustomize.py /var/lang/lib/python3.11/sitecustomize.py

# 4) Copy app
COPY app.py .

# 5) Build-time sanity check: verify shim + chromadb import
RUN python - <<'PY'
import sqlite3
print("sqlite_version:", sqlite3.sqlite_version)
import chromadb
print("chromadb_import: OK")
PY

CMD ["app.lambda_handler"]