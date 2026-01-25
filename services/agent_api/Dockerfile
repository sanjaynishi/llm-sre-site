FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

COPY requirements.txt .

# Install deps (single pass; deterministic)
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

# Build-time sanity check (safe)
RUN python - <<'PY'
import sys
import sqlite3
print("sqlite_version:", sqlite3.sqlite_version)
PY

COPY app.py .

CMD ["app.lambda_handler"]