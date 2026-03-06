FROM python:3.12-slim

RUN pip install --no-cache-dir numpy pandas scipy

RUN useradd --create-home --shell /bin/false sandbox
USER sandbox
WORKDIR /home/sandbox
