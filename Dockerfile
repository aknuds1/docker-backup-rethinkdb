FROM rethinkdb:2.3.6
MAINTAINER Arve Knudsen <arve.knudsen@gmail.com>

WORKDIR /app
ENTRYPOINT ["python3", "backup-database.py"]

RUN \
  apt-get update && \
  apt-get install -y python3 python3-pip && \
  rm -rf /var/lib/apt/lists/*

# Cache dependencies
COPY requirements.txt .
# python-daemon requires docutils, but the dependency isn't picked up by pip
RUn pip3 install -U docutils
RUN pip3 install -U -r requirements.txt

COPY ./ .
