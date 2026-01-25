FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# 1) Copy shim FIRST so Python auto-loads it on startup
COPY sitecustomize.py .

# 2) Copy requirements and install deps
COPY requirements.txt .

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

# 3) Build-time sanity check (this now uses shimmed sqlite)
RUN python - <<'PY'
import sqlite3
print("sqlite_version:", sqlite3.sqlite_version)
import chromadb
print("chromadb_import: OK")
PY

# 4) Copy app last (keeps Docker layer cache friendly)
COPY app.py .

CMD ["app.lambda_handler"]