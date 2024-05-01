FROM python:3.9.2-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
COPY src ./
CMD ["python", "/app/main.py"]

# For this dockerized service to work three volumes have to be passed:
# - The docker socket: /var/run/docker.sock
# - The docker binary: /usr/bin/docker
# - The docker compose plugin: /usr/libexec/docker/cli-plugins/docker-compose

# Apart from that you need to pass the base path where the compose files will be added.
