FROM public.ecr.aws/lambda/python:3.11

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ${LAMBDA_TASK_ROOT}/

# Lambda handler
CMD ["app.lambda_handler"]