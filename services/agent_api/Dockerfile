FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# 1) Dependencies
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

# 2) ✅ Ensure sqlite shim loads BEFORE anything imports sqlite3/chromadb
# Python auto-imports sitecustomize at startup if it's on sys.path.
COPY sitecustomize.py .

# 3) App code
COPY app.py .

# 4) Build-time sanity check: sqlite version + chromadb import
RUN python - <<'PY'
import sqlite3
print("sqlite_version:", sqlite3.sqlite_version)
import chromadb
print("chromadb_import: OK")
PY

CMD ["app.lambda_handler"]