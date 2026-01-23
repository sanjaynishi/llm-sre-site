FROM public.ecr.aws/lambda/python:3.11

# Optional but helpful for some wheels; you can keep if already present
RUN yum -y update && \
    yum -y install gcc gcc-c++ make cmake && \
    yum clean all

WORKDIR /var/task

COPY requirements.txt .

# Upgrade toolchain, install numpy first (binary wheel), then install the rest
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir "numpy==1.26.4" && \
    python -m pip install --no-cache-dir -r requirements.txt

COPY app.py .

# If your handler is app.lambda_handler
CMD ["app.lambda_handler"]