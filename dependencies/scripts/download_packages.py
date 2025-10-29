import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import click
import httpx
import stamina
from pydantic import BaseModel
from typing_extensions import Self, override

logger = logging.getLogger("weekly_download")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class BaseDataInterface(BaseModel, ABC):
    packages: list[str]
    date: str = datetime.now(ZoneInfo("UTC")).isoformat()

    def __len__(self) -> int:
        return len(self.packages)

    @classmethod
    @abstractmethod
    def from_packages_list(cls, packages: list[str]) -> Self: ...


class PypiDataInterface(BaseDataInterface):
    @override
    @classmethod
    def from_packages_list(cls, packages: list[str]) -> Self:
        return cls(packages=packages)


class NpmDataInterface(BaseDataInterface):
    @override
    @classmethod
    def from_packages_list(cls, packages: list[str]) -> Self:
        return cls(packages=packages)


class NpmFormattedDataInterface(BaseDataInterface):
    packages: list[str]
    namespaces: dict[str, list[str]]  # contains `namespace` as key, `packages` as strings in a list.

    def __len__(self) -> int:
        return len(self.packages) + sum([len(ns_packages) for _key, ns_packages in self.namespaces.items()])

    @override
    @classmethod
    def from_packages_list(cls, packages: list[str]) -> Self:
        namespaces: dict[str, list[str]] = {}
        namespace_packages = []
        for package in packages:
            if package.startswith("@"):
                namespace, package_name = package.split("/")
                if namespace not in namespaces:
                    namespaces[namespace] = []
                namespaces[namespace].append(package_name)
                namespace_packages.append(package)
        return cls(packages=list(set(packages).difference(set(namespace_packages))), namespaces=namespaces)


def parse_npm(data: list[dict[str, Any]]) -> list[str]:
    return [x["name"] for x in data]


def parse_pypi(data: dict[str, Any]) -> list[str]:
    return [row["project"] for row in data["rows"]]


class ServerError(Exception):
    """Custom exception for HTTP 5xx errors."""


@dataclass(frozen=True)
class Ecosystem:
    url: str
    params: dict[str, Any] | None
    pages: int | None
    parser: Callable[[dict[str, Any]], list[str]]
    data_interface: type[BaseDataInterface]


@dataclass(frozen=True)
class PypiEcosystem(Ecosystem):
    url = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json"
    params = None
    pages = None
    parser = parse_pypi
    data_interface = PypiDataInterface


@dataclass(frozen=True)
class NpmEcosystem(Ecosystem):
    url = "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages"
    params = {"per_page": 100, "sort": "downloads"}
    pages = 150
    parser = parse_npm
    data_interface = NpmDataInterface


@dataclass(frozen=True)
class NpmFormattedEcosystem(Ecosystem):
    url = "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages"
    params = {"per_page": 100, "sort": "downloads"}
    pages = 150
    parser = parse_npm
    data_interface = NpmFormattedDataInterface


ECOSYSTEMS: dict[str, type[Ecosystem]] = {
    "pypi": PypiEcosystem,
    "npm": NpmEcosystem,
    "npm_formatted": NpmFormattedEcosystem,
}


@click.group()
def entry_point() -> None:
    pass


@entry_point.command()
@click.argument(
    "ecosystem",
    type=str,
    required=True,
)
def download(
    ecosystem: str,
) -> None:
    if ecosystem not in ECOSYSTEMS:
        raise click.BadParameter("Not a valid ecosystem")

    selected_ecosystem = ECOSYSTEMS[ecosystem]
    n_pages = selected_ecosystem.pages or 1
    all_packages: list[str] = []

    for page in range(150, n_pages + 1 + 150):
        params = selected_ecosystem.params or {}
        if selected_ecosystem.pages:
            params["page"] = page

        all_packages.extend(get_packages(selected_ecosystem.url, selected_ecosystem.parser, params))

    fpath = Path("dependencies") / f"{ecosystem}.json"
    data = selected_ecosystem.data_interface.from_packages_list(all_packages)
    save_data_to_file(data, fpath)


def get_packages(
    base_url: str, parser: Callable[[dict[str, Any]], list[str]], params: dict[str, Any] | None = None
) -> list[str]:
    for attempt in stamina.retry_context(
        on=(httpx.TransportError, httpx.TimeoutException, ServerError),
        attempts=10,
        wait_jitter=1,
        wait_exp_base=2,
        wait_max=8,
    ):
        with attempt, httpx.Client(timeout=90) as client:
            response = client.get(str(base_url), params=params)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.is_server_error:
                    raise ServerError from e
    return parser(response.json())


def save_data_to_file(
    data: BaseDataInterface,
    fpath: Path,
) -> None:
    with open(str(fpath), "w") as fp:
        json.dump(data.model_dump(), fp)

    logger.info("Saved %d packages to `%s` file.", len(data), fpath)


if __name__ == "__main__":
    entry_point()
