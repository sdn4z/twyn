import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

import requests

from twyn.file_handler.exceptions import PathIsNotFileError, PathNotFoundError
from twyn.file_handler.file_handler import FileHandler
from twyn.trusted_packages.exceptions import (
    EmptyPackagesListError,
    InvalidJSONError,
    InvalidPyPiFormatError,
)

logger = logging.getLogger("twyn")

CACHE_TTL = 60 * 60 * 24  # 1 day, in seconds


@dataclass
class CachedDependencies:
    udpated_at: int
    dependencies: list[str]

    def is_cache_available(self) -> bool:
        return bool((datetime.now().timestamp() - self.udpated_at) < CACHE_TTL)


class AbstractPackageReference(ABC):
    """Represents a reference to retrieve trusted packages from."""

    def __init__(self, source: str, file_handler: FileHandler) -> None:
        self.source = source
        self.file_handler = file_handler

        self.file_handler.create_if_does_not_exist()

    @abstractmethod
    def _parse(self) -> set[str]:  # TODO okay to have a ABC with just one abstratmethod?
        """Parse trusted dependencies."""

    def get_packages(self) -> set[str]:
        """
        Retrieve and parse online source.

        If cache is available, it will return it. It will write to it otherwise.
        """
        if cache := self._read_cache():
            return cache

        packages_info = self._download()
        parsed_packages = self._parse(packages_info)
        self._write_cache(parsed_packages)
        return parsed_packages

    def _read_cache(self) -> Optional[CachedDependencies]:
        """Return the packages from a cached file. If the cached file is not present or the cache is expired returns None."""
        try:
            data = CachedDependencies(**self.file_handler.read_json())
            if data.is_cache_available():
                return data.dependencies
            else:
                return None
        except (PathIsNotFileError, PathNotFoundError):
            logger.debug("Could not read from local cache file.")
            return None

    def _write_cache(self, data: list[str]) -> None:
        try:
            # TODO weird to create it and right after that cast it to a dict.
            new_content = CachedDependencies(udpated_at=datetime.now().timestamp(), dependencies=data)
            self.file_handler.write_json(asdict(new_content))
        except (PathIsNotFileError, PathNotFoundError):
            logger.debug("Could not write to local cache file.")

    def _download(
        self,
    ) -> dict[str, Any]:  # TODO evaluate: return dataclass, that's able to parse to the desired format
        packages = requests.get(self.source)
        packages.raise_for_status()
        try:
            packages_json: dict[str, Any] = packages.json()
        except requests.exceptions.JSONDecodeError as err:
            raise InvalidJSONError from err

        logger.debug(f"Successfully downloaded trusted packages list from {self.source}")

        return packages_json


class TopPyPiReference(AbstractPackageReference):
    """Top PyPi packages retrieved from an online source."""

    @staticmethod
    def _parse(packages_info: dict[str, Any]) -> set[str]:
        try:
            names = {row["project"] for row in packages_info["rows"]}
        except KeyError as err:
            raise InvalidPyPiFormatError from err

        if not names:
            raise EmptyPackagesListError

        logger.debug("Successfully parsed trusted packages list")

        return names
