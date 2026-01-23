FROM public.ecr.aws/lambda/python:3.11

# Set workdir
WORKDIR /var/task

# ---- Install Python dependencies ----
# Copy requirements first for layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy app code ----
COPY app.py .

# Lambda handler
CMD ["app.lambda_handler"]