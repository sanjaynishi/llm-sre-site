FROM public.ecr.aws/lambda/python:3.11

# Tooling for packages that may need compilation
RUN yum -y update && \
    yum -y install gcc gcc-c++ make cmake && \
    yum clean all

WORKDIR /var/task

COPY requirements.txt .

# Upgrade pip toolchain + verbose output so the real failing package is visible
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -v -r requirements.txt

COPY app.py .

CMD ["app.lambda_handler"]