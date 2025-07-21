from functools import cached_property
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class RustcErrorText(BaseModel):
    class Config:
        frozen = True

    text: str
    highlight_start: int
    highlight_end: int


class RustcErrorSpan(BaseModel):
    class Config:
        frozen = True

    file_name: str
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    column_start: int
    column_end: int
    is_primary: bool
    text: tuple["RustcErrorText", ...]
    label: str | None
    suggested_replacement: str | None
    suggestion_applicability: str | None
    expansion: "RustcErrorExpansion | None"


class RustcErrorCode(BaseModel):
    class Config:
        frozen = True

    code: str
    explanation: str | None


class RustcErrorExpansion(BaseModel):
    class Config:
        frozen = True

    span: RustcErrorSpan
    macro_decl_name: str
    def_site_span: RustcErrorSpan | None


class RustcErrorMessages(BaseModel):
    class Config:
        frozen = True

    message_type: str | None = Field(alias="$message_type", default=None)  # type: ignore
    message: str
    level: Literal[
        "error",
        "warning",
        "note",
        "help",
        "failure-note",
        "error: internal compiler error",
    ]
    code: RustcErrorCode | None
    spans: tuple[RustcErrorSpan, ...]
    children: tuple["RustcErrorMessages", ...]
    rendered: str | None

    @cached_property
    def all_spans(self) -> list[RustcErrorSpan]:
        spans = list(self.spans)
        for child in self.children:
            spans.extend(child.spans)
        unfolded = []
        for span in spans:
            while span.expansion:
                def_site_span = span.expansion.def_site_span
                if def_site_span and def_site_span.byte_start != 0:
                    unfolded.append(def_site_span)
                span = span.expansion.span
            unfolded.append(span)
        return unfolded


class CargoOutputTarget(BaseModel):
    kind: list[str]
    crate_types: list[str]
    name: str
    src_path: str
    edition: str
    doc: bool
    doctest: bool
    test: bool


class CargoOutputProfile(BaseModel):
    opt_level: str
    debuginfo: int
    debug_assertions: bool
    overflow_checks: bool
    test: bool


class CargoMessageCompilerMessage(BaseModel):
    reason: Literal["compiler-message"]
    package_id: str

    manifest_path: str
    target: CargoOutputTarget

    message: RustcErrorMessages


class CargoMessageCompilerArtifact(BaseModel):
    reason: Literal["compiler-artifact"]
    package_id: str

    manifest_path: str
    target: CargoOutputTarget

    profile: CargoOutputProfile
    features: list[str]
    filenames: list[str]
    executable: str | None
    fresh: bool


class CargoMessageBuildScriptExecuted(BaseModel):
    reason: Literal["build-script-executed"]
    package_id: str

    linked_libs: list[str]
    linked_paths: list[str]
    cfgs: list[str]
    env: list[tuple[str, str]]
    out_dir: str


class CargoMessageBuildFinished(BaseModel):
    reason: Literal["build-finished"]
    success: bool


CargoMessage = Annotated[
    CargoMessageCompilerMessage
    | CargoMessageCompilerArtifact
    | CargoMessageBuildScriptExecuted
    | CargoMessageBuildFinished,
    Field(discriminator="reason"),
]

CargoMessageTypeAdapter: TypeAdapter[CargoMessage] = TypeAdapter(CargoMessage)
