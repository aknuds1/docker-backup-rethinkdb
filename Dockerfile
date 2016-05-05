FROM rethinkdb:2.3
MAINTAINER Arve Knudsen <arve.knudsen@gmail.com>

WORKDIR /app
ENTRYPOINT ["python3", "backup-database.py"]

RUN \
  apt-get update && \
  apt-get install -y python3 python-pip3 && \
  rm -rf /var/lib/apt/lists/*

COPY ./ .
RUN pip3 install -r requirements.txt
