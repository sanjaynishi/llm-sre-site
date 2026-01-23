FROM public.ecr.aws/lambda/python:3.11

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app.py ${LAMBDA_TASK_ROOT}/app.py

# Lambda handler
CMD ["app.lambda_handler"]