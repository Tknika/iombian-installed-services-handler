import logging
import os
import pathlib
from threading import Timer
from typing import List, Optional

from python_on_whales import DockerClient, docker
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)


class InstalledServiceHandler(FileSystemEventHandler):
    """Handler of a service on the "iombian-services" folder.

    When a change occurs on the service the compose restarts.
    """

    ACCEPTED_FILES = ["docker-compose.yaml", "docker-compose.yml", ".env"]
    ACCEPTED_EVENTS = ["modified", "created", "deleted"]

    service_path: str
    """The full path of the service"""
    service_name: str
    """The name of the service"""
    wait_seconds: float
    """Seconds to wait between changes before restarting the service compose"""
    timer: Optional[Timer]
    """The timer used for waiting the `wait_seconds` time"""
    observer: BaseObserver
    """The `Observer` of the service folder"""
    files: List[str]
    """The list of the files in the service folder"""
    docker: Optional[DockerClient]
    """The docker client of the service compose"""

    def __init__(self, service_path: str, wait_seconds: float):
        self.service_path = service_path
        self.service_name = service_path.split("/")[-1]
        self.wait_seconds = wait_seconds
        self.timer = None
        self.observer = Observer()
        self.files = os.listdir(service_path)
        self.docker = self._get_docker()

    def start(self):
        """Start the handler by starting the observer of the service folder."""
        try:
            self.observer.schedule(self, self.service_path, recursive=True)
            self.observer.start()
            logger.debug(f"{self.service_name} Installed Service Handler started.")
        except FileNotFoundError:
            logger.error(
                f"Couldn't start a watcher for the {self.service_name} service, the folder no longer exists."
            )
            self.down()

    def stop(self):
        """Stop the handler by stopping the observer of the service folder."""
        logger.debug("Installed Service Handler stopped.")
        self.observer.stop()

    def up(self):
        """Start the compose of the service by doing "docker compose up"."""
        if self.docker:
            try:
                self.docker.compose.up(detach=True)
                logger.info(f"{self.service_name} service compose started.")
            except:
                logger.error(
                    f"An error occurred, couldn't start service {self.service_name}."
                )

    def down(self):
        """Stop the compose of the service.

        This is done by getting the containers started by the compose file and killing them.
        The volumes are pruned to remove any unused ones.

        This is done like this because, when the service folder is removed the compose needs to stop.
        But, in that case, the compose file no longer exists, so "docker compose down" can't be called.
        """
        if self.docker:
            logger.info(f"{self.service_name} service compose stopped.")
            containers = self.docker.ps(
                filters={
                    "label": f"com.docker.compose.project.config_files={self.service_path}/{self.compose_file}"
                }
            )
            for container in containers:
                docker.container.stop(container)
                docker.container.remove(container)

            docker.volume.prune()

    def reload_service_compose(self):
        """Stop the compose, get the docker client again and start the compose.

        The docker client is loaded again because, if the compose file is changed, the docker client will not be valid.
        """
        if not (self.docker and self.compose_file):
            return

        logger.debug(f"{self.service_name} service modified.")

        self.down()
        self.docker = self._get_docker()
        self.up()

        self.timer = None

    def on_any_event(self, event: FileSystemEvent):
        """Reload the service when the service changes.

        The service changes when the docker-compose file or the .env file changes in the first level of the folder.

        """
        if event.is_directory:
            return

        path = pathlib.Path(event.src_path)
        file = path.name
        folder = path.parts[-2]

        if (
            file in self.ACCEPTED_FILES
            and folder == self.service_name
            and event.event_type in self.ACCEPTED_EVENTS
        ):
            if self.timer:
                self.timer.cancel()
                self.timer = None

            self.timer = Timer(self.wait_seconds, self.reload_service_compose)
            self.timer.start()

    def _get_compose_file_name(self):
        """Get the name of the compose file in the service.

        This can be "docker-compose.yaml" of "docker-compose.yml".
        """
        if "docker-compose.yaml" in self.files:
            return "docker-compose.yaml"
        elif "docker-compose.yml" in self.files:
            return "docker-compose.yml"

    def _get_docker(self):
        """Get the docker client of the compose of the service."""
        self.compose_file = self._get_compose_file_name()
        if self.compose_file:
            return DockerClient(
                compose_files=[f"{self.service_path}/{self.compose_file}"]
            )
