FROM python:3.9-slim

WORKDIR /spotify
COPY requirements.txt spotify.py templates static ./
RUN pip install -r requirements.txt
CMD python spotify.py