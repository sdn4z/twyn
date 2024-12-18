import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol

from twyn.file_handler.exceptions import CannotCreateFileError, PathIsNotFileError, PathNotFoundError

logger = logging.getLogger("twyn")


class BaseFileHandler(Protocol):
    def read(self) -> str: ...
    def file_exists(self) -> bool: ...
    def write(self, data: str) -> None: ...


class FileHandler(BaseFileHandler):
    def __init__(self, file_path: str) -> None:
        self.file_path = self._get_file_path(file_path)

    def _get_file_path(self, file_path: str) -> Path:
        return Path(os.path.abspath(os.path.join(os.getcwd(), file_path)))

    def is_handler_of_file(self, name: str) -> bool:
        return self._get_file_path(name) == self.file_path

    def read(self) -> str:
        self._raise_for_file_exists()

        content = self.file_path.read_text()

        return content

    def read_json(self) -> dict[str, Any]:
        self._raise_for_file_exists()
        content = json.load(self.file_path.open())
        return content

    def write_json(self, content: dict[str, Any]) -> None:
        self._raise_for_file_exists()
        json.dump(content, self.file_path.open())

    def file_exists(self) -> bool:
        try:
            self._raise_for_file_exists()
        except (PathNotFoundError, PathIsNotFileError):
            return False
        return True

    def _raise_for_file_exists(self) -> None:
        if not self.file_path.exists():
            raise PathNotFoundError

        if not self.file_path.is_file():
            raise PathIsNotFileError

    def write(self, data: str) -> None:
        self._raise_for_file_exists()
        self.file_path.write_text(data)

    def create_if_does_not_exist(self) -> None:
        if not self.file_exists():
            try:
                self.file_path.touch()
            except Exception as e:
                raise CannotCreateFileError from e
