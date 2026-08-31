from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .project import BuckyProject, ModuleInfo


@dataclass(frozen=True)
class BuildArtifact:
    role: str
    path: Path
    kind: str
    install_name: str | None = None
    executable: bool = False


@dataclass(frozen=True)
class BuildResultSpec:
    build_type: str
    required_artifact_roles: tuple[str, ...] = ()


@dataclass
class BuildResult:
    module_key: str
    build_type: str
    work_dir: Path
    artifacts: List[BuildArtifact] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)

    def validate(self, spec: BuildResultSpec) -> None:
        if self.build_type != spec.build_type:
            raise ValueError(
                f"BuildResult for {self.module_key} has type {self.build_type}, expected {spec.build_type}"
            )
        if not self.work_dir.is_dir():
            raise ValueError(f"BuildResult work directory does not exist: {self.work_dir}")
        roles = {artifact.role for artifact in self.artifacts}
        missing = set(spec.required_artifact_roles) - roles
        if missing:
            raise ValueError(
                f"BuildResult for {self.module_key} is missing artifact role(s): {', '.join(sorted(missing))}"
            )


@dataclass(frozen=True)
class BuildContext:
    rust_target: str
    full_build: bool = True
    timings: bool = False
    timings_dir: Path | None = None


@dataclass(frozen=True)
class InstallReference:
    app_name: str
    install_path: str
    staging_path: Path


@dataclass(frozen=True)
class MaterializedArtifact:
    module_key: str
    build_type: str
    format: str
    source_path: Path
    install_app: str
    install_path: str
    size: int | None = None
    digest: str | None = None


class Builder(Protocol):
    build_type: str

    def plan(self, module_key: str, module: "ModuleInfo") -> BuildResultSpec:
        ...

    def build_modules(
        self,
        project: "BuckyProject",
        module_keys: List[str],
        context: BuildContext,
    ) -> Dict[str, BuildResult]:
        ...


class Formatter(Protocol):
    format_name: str
    supported_build_types: frozenset[str] | None

    def materialize(
        self,
        project: "BuckyProject",
        module_key: str,
        result: BuildResult,
        install_references: List[InstallReference],
    ) -> List[MaterializedArtifact]:
        ...


class BuilderRegistry:
    def __init__(self, builders: Iterable[Builder] = ()) -> None:
        self._builders: Dict[str, Builder] = {}
        for builder in builders:
            self.register(builder)

    def register(self, builder: Builder) -> None:
        if builder.build_type in self._builders:
            raise ValueError(f"Builder already registered: {builder.build_type}")
        self._builders[builder.build_type] = builder

    def require(self, build_type: str) -> Builder:
        try:
            return self._builders[build_type]
        except KeyError as error:
            raise ValueError(f"Unknown module type: {build_type}") from error


class FormatterRegistry:
    def __init__(self, formatters: Iterable[Formatter] = ()) -> None:
        self._formatters: Dict[str, Formatter] = {}
        for formatter in formatters:
            self.register(formatter)

    def register(self, formatter: Formatter) -> None:
        if formatter.format_name in self._formatters:
            raise ValueError(f"Formatter already registered: {formatter.format_name}")
        self._formatters[formatter.format_name] = formatter

    def require(self, format_name: str) -> Formatter:
        try:
            return self._formatters[format_name]
        except KeyError as error:
            raise ValueError(f"Unknown module format: {format_name}") from error


def collect_install_references(
    project: "BuckyProject",
    module_key: str,
) -> List[InstallReference]:
    references: List[InstallReference] = []
    for app_name, app_info in project.apps.items():
        install_path = app_info.modules.get(module_key)
        if install_path is None:
            continue
        staging_path = project.resolve_from_base_dir(app_info.rootfs) / install_path
        references.append(
            InstallReference(
                app_name=app_name,
                install_path=install_path,
                staging_path=staging_path,
            )
        )
    return references
