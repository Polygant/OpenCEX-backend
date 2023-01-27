FROM python:3.8
ENV PYTHONUNBUFFERED 1
WORKDIR /app
COPY requirements.txt /tmp/
RUN pip install setuptools==40
RUN pip install  --no-cache-dir -r /tmp/requirements.txt
RUN apt-get update && apt-get install systemd gettext -y