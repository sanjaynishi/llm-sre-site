FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

COPY requirements.txt .

# Install deps
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir "numpy==1.26.4" && \
    python -m pip install --no-cache-dir -r requirements.txt

# Prove sqlite shim works inside the built image (build-time safety check)
RUN python - <<'PY'
import sys
import pysqlite3.dbapi2 as sqlite3
sys.modules["sqlite3"] = sqlite3
import sqlite3 as s
print("sqlite_version:", s.sqlite_version)
PY

COPY app.py .

CMD ["app.lambda_handler"]