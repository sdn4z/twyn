from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from typing_extensions import Self

from twyn.similarity.algorithm import (
    AbstractSimilarityAlgorithm,
    SimilarityThreshold,
)
from twyn.trusted_packages.managers.base import OrderedPackages
from twyn.trusted_packages.models import TyposquatCheckResultEntry
from twyn.trusted_packages.selectors import AbstractSelector


@dataclass
class NamespaceDependency:
    package: str
    namespace: str | None = None

    @property
    def full_name(self) -> str:
        if self.namespace:
            return f"{self.namespace}/{self.package}"
        return self.package

    @classmethod
    def from_name(cls, name: str) -> Self:
        if name.startswith("@"):
            namespace, package = name.split("/")
            return cls(package=package, namespace=namespace)
        return cls(package=name)


class TrustedNpmPackageManager:
    """Representation of namespaces that can be trusted."""

    def __init__(
        self,
        names: set[str],
        algorithm: AbstractSimilarityAlgorithm,
        selector: AbstractSelector,
        threshold_class: type[SimilarityThreshold],
    ) -> None:
        self.packages, self.namespaces = self._create_names_dictionary(names)

        self.threshold_class = threshold_class
        self.selector = selector
        self.algorithm = algorithm

    def __contains__(self, obj: Any) -> bool:
        """Check if an object exists in the trusted namespaces."""
        if isinstance(obj, str):
            return obj in self.packages[obj[0]] or obj in self.namespaces
        return False

    def _create_names_dictionary(self, names: set[str]) -> tuple[OrderedPackages, OrderedPackages]:
        """Create a dictionary which will group all packages that start with the same letter under the same key."""
        first_letter_names: OrderedPackages = defaultdict(set)
        namespaces: OrderedPackages = defaultdict(set)
        for name in names:
            dependency = NamespaceDependency.from_name(name)
            if dependency.namespace:
                if dependency.namespace not in namespaces:
                    namespaces[dependency.namespace] = set()
                namespaces[dependency.namespace].add(dependency.package)
            else:
                first_letter_names[name[0]].add(dependency.package)
        return first_letter_names, namespaces

    def _get_typosquats_from_namespace_dependency(self, dependency: NamespaceDependency) -> Any:
        threshold = self.threshold_class.from_name(dependency.namespace)
        typosquat_result = TyposquatCheckResultEntry(dependency=dependency.full_name)
        for trusted_namespace_name in self.selector.select_similar_names(
            names=self.namespaces.keys(), name=dependency.namespace
        ):
            distance = self.algorithm.get_distance(dependency.namespace, trusted_namespace_name)
            if (
                threshold.is_inside_threshold(distance)
                and dependency.package in self.namespaces[trusted_namespace_name]
            ):
                typosquat_result.add(trusted_namespace_name)

    def _get_typosquats_from_dependency(self, dependency: NamespaceDependency) -> Any:
        threshold = self.threshold_class.from_name(dependency.package)
        typosquat_result = TyposquatCheckResultEntry(dependency=dependency.package)
        for trusted_package_name in self.selector.select_similar_names(names=self.packages, name=dependency.package):
            distance = self.algorithm.get_distance(dependency.package, trusted_package_name)
            if threshold.is_inside_threshold(distance):
                typosquat_result.add(trusted_package_name)
        return typosquat_result

    def get_typosquat(self, package_name: str) -> TyposquatCheckResultEntry:
        """Check if a given package name is similar to any trusted package and returns it.

        Only if there is a match on the first letter can a package name be
        considered similar to another one. The algorithm provided and the threshold
        are used to determine if the package name can be considered similar.
        """
        dependency = NamespaceDependency.from_name(package_name)
        if dependency.namespace:
            return self._get_typosquats_from_namespace_dependency(dependency)
        return self._get_typosquats_from_dependency(dependency)
