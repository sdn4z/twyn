import logging
import re

from typing_extensions import override

from twyn.trusted_packages.exceptions import (
    PackageNormalizingError,
)
from twyn.trusted_packages.references.base import AbstractPackageReference, NormalizedPackages

logger = logging.getLogger("twyn")


class TopNpmReference(AbstractPackageReference):
    """Top npm packages retrieved from an online source."""

    DEFAULT_SOURCE: str = (
        "https://raw.githubusercontent.com/elementsinteractive/twyn/refs/heads/main/dependencies/npm.json"
    )
    """Default URL for fetching top npm packages."""

    @override
    @staticmethod
    def normalize_packages(packages: set[str], namespaces: dict[str, list[str]] | None = None) -> NormalizedPackages:
        """Normalize dependency names according to npm."""
        if not packages:
            logger.debug("Tried to normalize packages, but none were provided")
            return NormalizedPackages(packages=set())

        # If namespaces are provided from cache, convert them to sets and return
        if namespaces:
            namespaces_sets = {ns: set(pkgs) for ns, pkgs in namespaces.items()}
            return NormalizedPackages(packages=packages, namespaces=namespaces_sets)

        # Otherwise, extract namespaces from package names
        package_pattern = re.compile(r"^[a-z0-9-~][a-z0-9-._~]*$")  # noqa: F821
        namespace_pattern = re.compile(r"^(?:@[a-z0-9-~][a-z0-9-._~]*)\/[a-z0-9-~][a-z0-9-._~]*$")  # noqa: F821

        extracted_namespaces: dict[str, set[str]] = {}
        packages_set = set()
        for package in packages:
            if namespace_pattern.match(package.lower()):
                namespace, namespace_package = package.split("/")
                if namespace not in extracted_namespaces:
                    extracted_namespaces[namespace] = set()
                extracted_namespaces[namespace].add(namespace_package)
            elif package_pattern.match(package.lower()):
                packages_set.add(package)
            else:
                raise PackageNormalizingError(f"Package name '{package}' does not match required pattern")

        return NormalizedPackages(packages=packages, namespaces=extracted_namespaces)
