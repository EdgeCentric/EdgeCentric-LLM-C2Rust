from typing import Dict, List, Literal, Optional, Union

import toml
from pydantic import BaseModel, ConfigDict, HttpUrl, ValidationError


class CargoFeatures(BaseModel):
    features: List[str]


class Package(BaseModel):
    name: str
    version: str
    authors: List[str]
    edition: Optional[str] = None
    rust_version: Optional[str] = None
    description: Optional[str] = None
    documentation: Optional[HttpUrl] = None
    readme: Optional[str] = None
    homepage: Optional[HttpUrl] = None
    repository: Optional[HttpUrl] = None
    license: Optional[str] = None
    license_file: Optional[str] = None
    keywords: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    workspace: Optional[str] = None
    build: Optional[str] = None
    links: Optional[str] = None
    exclude: Optional[List[str]] = None
    include: Optional[List[str]] = None
    publish: Optional[bool] = None
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None
    default_run: Optional[str] = None
    autobins: Optional[bool] = None
    autoexamples: Optional[bool] = None
    autotests: Optional[bool] = None
    autobenches: Optional[bool] = None
    resolver: Optional[str] = None


class Dependency(BaseModel):
    version: str
    git: Optional[HttpUrl] = None
    branch: Optional[str] = None
    tag: Optional[str] = None
    rev: Optional[str] = None
    path: Optional[str] = None
    registry: Optional[str] = None
    features: Optional[List[str]] = None

    class Config:
        extra = "forbid"


class PlatformTarget(BaseModel):
    target: Optional[Dict[str, Dict[str, Union[str, bool, List[str]]]]] = None


class Target(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda field_name: field_name.replace("_", "-")
    )
    name: str
    path: str = "src/lib.rs"
    test: Optional[bool] = None
    doctest: Optional[bool] = None
    bench: Optional[bool] = None
    doc: Optional[bool] = None
    proc_macro: Optional[bool] = None
    harness: Optional[bool] = None
    edition: Optional[str] = None
    crate_type: Optional[
        List[
            Literal["bin", "lib", "dylib", "staticlib", "cdylib", "rlib", "proc-macro"]
        ]
    ] = None
    required_features: Optional[List[str]] = None


class CargoConfig(BaseModel):
    cargo_features: Optional[CargoFeatures] = None
    package: Optional[Package] = None
    lib: Optional[Target] = None
    bin: Optional[List[Target]] = None
    example: Optional[List[Dict[str, Union[str, bool]]]] = None
    test: Optional[List[Dict[str, Union[str, bool]]]] = None
    bench: Optional[List[Dict[str, Union[str, bool]]]] = None
    dependencies: Optional[dict[str, Union[str, Dependency]]] = None
    dev_dependencies: Optional[Dict[str, Union[str, Dependency]]] = None
    build_dependencies: Optional[Dict[str, Union[str, Dependency]]] = None
    target: Optional[PlatformTarget] = None
    badges: Optional[Dict[str, Dict[str, Union[str, bool]]]] = None
    features: Optional[Dict[str, List[str]]] = None
    patch: Optional[Dict[str, Dict[str, Union[str, bool, List[str]]]]] = None
    replace: Optional[Dict[str, Dict[str, Union[str, bool, List[str]]]]] = None
    profile: Optional[Dict[str, Dict[str, Union[str, bool, int, float]]]] = None
    workspace: Optional[Dict[str, Union[str, List[str]]]] = None


def encode_cargo_config(cargo_config: CargoConfig) -> str:

    cargo_dict: Dict = cargo_config.model_dump(exclude_none=True)

    toml_str = toml.dumps(cargo_dict)

    return toml_str


def write_cargo_config(cargo_config: CargoConfig, path: str):

    cargo_dict: Dict = cargo_config.model_dump(exclude_none=True)

    with open(path, "w", encoding="utf-8") as file:
        toml.dump(cargo_dict, file)


def decode_cargo_config(toml_str: str) -> CargoConfig:

    cargo_dict = toml.loads(toml_str)
    cargo_config = CargoConfig(**cargo_dict)
    return cargo_config


def read_cargo_config(path: str) -> CargoConfig:

    with open(path, "r", encoding="utf-8") as file:
        cargo_dict = toml.load(file)

    try:
        cargo_config = CargoConfig(**cargo_dict)
    except ValidationError as e:
        print("Invalid data in read TOML file:", e)
        raise

    return cargo_config
