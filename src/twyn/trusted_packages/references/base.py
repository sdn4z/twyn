import logging
from abc import abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from twyn.trusted_packages.cache_handler import CacheEntry, CacheHandler
from twyn.trusted_packages.exceptions import (
    EmptyPackagesListError,
    InvalidJSONError,
)

logger = logging.getLogger("twyn")


@dataclass
class NormalizedPackages:
    packages: set[str]
    namespaces: dict[str, set[str]] | None = None

    def __iter__(self) -> Iterator[str]:
        yield from self.packages

        if not self.namespaces:
            return

        for namespace in self.namespaces:
            for package_name in self.namespaces[namespace]:
                yield f"{namespace}/{package_name}"

    def __contains__(self, value: str) -> bool:
        if not isinstance(value, str):
            return False

        return value in self.packages or value in self._get_namespace_packages()

    def _get_namespace_packages(self) -> set[str]:
        packages_names = set()
        if not self.namespaces:
            return set()

        for namespace in self.namespaces:
            for package_name in self.namespaces[namespace]:
                packages_names.add(f"{namespace}/{package_name}")
        return packages_names


class AbstractPackageReference:
    """Represents a reference from where to retrieve trusted packages.

    It abstracts all the package-retrieval and caching logic.

    It defines the `_parse` abstract method, so each subclass defines how to handle the feched data.
    It defines the `normalize_package` abstract method, so each subclass validates that the packages names are correct.
    """

    DEFAULT_SOURCE: str
    """Default URL source for fetching trusted packages."""

    def __init__(self, source: str | None = None, cache_handler: CacheHandler | None = None) -> None:
        self.source = source or self.DEFAULT_SOURCE
        self.cache_handler = cache_handler

    @staticmethod
    @abstractmethod
    def normalize_packages(packages: set[str], namespaces: dict[str, list[str]] | None = None) -> NormalizedPackages:
        """Normalize package names to make sure they're valid within the package manager context."""

    def _download(self) -> dict[str, Any]:
        """Download data from the source URL."""
        response = requests.get(self.source)
        response.raise_for_status()

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as err:
            raise InvalidJSONError from err

    def _save_trusted_packages_to_cache_if_enabled(
        self, packages: set[str], namespaces: dict[str, list[str]] | None = None
    ) -> None:
        """Save trusted packages using CacheHandler."""
        if not self.cache_handler:
            return
        cache_entry = CacheEntry(saved_date=datetime.now().date().isoformat(), packages=packages, namespaces=namespaces)
        self.cache_handler.write_entry(self.source, cache_entry)
        logger.debug("Saved %d trusted packages for source %s", len(packages), self.source)

    def _get_packages_from_cache_if_enabled(self) -> tuple[set[str], dict[str, list[str]] | None]:
        """Get packages and namespaces from cache if it's present and up to date."""
        if not self.cache_handler:
            return set(), None
        cache_entry = self.cache_handler.get_cache_entry(self.source)
        if not cache_entry:
            logger.debug("No cache entry found for source: %s", self.source)
            return set(), None

        return cache_entry.packages, cache_entry.namespaces

    def get_packages(self) -> NormalizedPackages:
        """Download and parse online source of top packages from the package ecosystem."""
        packages, namespaces = self._get_packages_from_cache_if_enabled()
        # we don't save the cache here, we keep it as it is so the date remains the original one.
        if not packages:
            # no cache usage, no cache hit (non-existent or outdated) or cache was empty.
            logger.info("Fetching trusted packages from trusted packages reference...")
            data = self._download()
            try:
                packages = set(data["packages"])
            except KeyError as err:
                raise InvalidJSONError("`packages` key not in JSON.") from err

            logger.debug("Successfully downloaded trusted packages list from %s", self.source)
            if not packages:
                raise EmptyPackagesListError

            # Normalize packages to extract namespaces for caching
            normalized = self.normalize_packages(packages)

            # Convert namespaces from sets to lists for JSON serialization
            namespaces_for_cache = {}
            if normalized.namespaces:
                namespaces_for_cache = {ns: sorted(pkgs) for ns, pkgs in normalized.namespaces.items()}

            # New packages were downloaded, we create a new entry updating all values.
            self._save_trusted_packages_to_cache_if_enabled(packages, namespaces_for_cache)

            return normalized

        return self.normalize_packages(packages, namespaces)
