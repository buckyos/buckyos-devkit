import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

from .buckyos_kit import get_execute_name
from .module_build import (
    BuildResult,
    InstallReference,
    MaterializedArtifact,
)
from .project import BuckyProject, PikgModuleConfig, RustModuleInfo


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_BUCKYOS_NPX = ("npx", "--yes", "buckyos@latest")


def _buckyos_command() -> List[str]:
    configured = os.environ.get("BUCKYOS_PIKG_COMMAND")
    if configured is None:
        return list(_BUCKYOS_NPX)
    command = json.loads(configured)
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("BUCKYOS_PIKG_COMMAND must be a JSON array of command arguments")
    return command


def _read_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"{label} not found: {path}")
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read {label} at {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _require_string(value: Dict[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return result


def _require_integer(value: Dict[str, Any], key: str, label: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise ValueError(f"{label}.{key} must be a non-negative integer")
    return result


def _resolve_cli_path(value: str, cwd: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def _shell_command(argv: List[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def _run_buckyos_json(argv: List[str], cwd: Path) -> Dict[str, Any]:
    command = _shell_command(argv)
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        detail = f"\n{result.stdout.strip()}" if result.stdout.strip() else ""
        raise RuntimeError(
            f"{' '.join(argv)} failed with exit code {result.returncode}{detail}"
        )
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"{' '.join(argv)} returned invalid JSON: {error}") from error
    if not isinstance(envelope, dict):
        raise ValueError(f"{' '.join(argv)} did not return a JSON object")
    if envelope.get("schema_version") != 1:
        raise ValueError(f"{' '.join(argv)} returned an unsupported envelope schema")
    if envelope.get("ok") is not True:
        raise ValueError(f"{' '.join(argv)} returned a non-success envelope")
    data = envelope.get("data")
    meta = envelope.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict):
        raise ValueError(f"{' '.join(argv)} returned an invalid success envelope")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _metadata_sources(meta_dir: Path, pikg: Dict[str, Any]) -> List[Path]:
    subpackages = pikg.get("sub_pkgs")
    if not isinstance(subpackages, dict) or not subpackages:
        raise ValueError("pikg.json.sub_pkgs must be a non-empty object")
    sources: List[Path] = []
    seen = set()
    for key, raw_subpackage in subpackages.items():
        if not isinstance(raw_subpackage, dict):
            raise ValueError(f"pikg.json.sub_pkgs.{key} must be an object")
        source = raw_subpackage.get("source")
        if not isinstance(source, dict):
            raise ValueError(f"pikg.json.sub_pkgs.{key}.source must be an object")
        if source.get("type") != "path":
            continue
        value = source.get("path")
        if not isinstance(value, str) or not value:
            raise ValueError(f"pikg.json.sub_pkgs.{key}.source.path must be a non-empty string")
        try:
            resolved = (meta_dir / value).resolve(strict=True)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"PIKG source for subpackage {key} does not exist: {meta_dir / value}"
            ) from error
        if not resolved.is_dir() and not (
            resolved.is_file() and resolved.name.lower().endswith(".tar.gz")
        ):
            raise ValueError(
                f"PIKG source for subpackage {key} must be a directory or .tar.gz file: {resolved}"
            )
        key_path = os.path.normcase(str(resolved))
        if key_path not in seen:
            seen.add(key_path)
            sources.append(resolved)
    return sources


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _transactional_install(
    source: Path,
    targets: List[Path],
    expected_size: int,
    expected_digest: str,
) -> None:
    prepared: List[Dict[str, Any]] = []
    unique_targets: List[Path] = []
    seen = set()
    for target in targets:
        resolved = Path(os.path.abspath(target))
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique_targets.append(resolved)

    try:
        for target in unique_targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError(f"PIKG staging target must be a regular file: {target}")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            backup = target.with_name(f".{target.name}.{uuid.uuid4().hex}.bak")
            item = {
                "target": target,
                "temporary": temporary,
                "backup": backup,
                "had_target": target.exists(),
                "installed": False,
            }
            prepared.append(item)
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != expected_size or _sha256(temporary) != expected_digest:
                raise ValueError(f"PIKG staging copy verification failed: {temporary}")

        for item in prepared:
            target = item["target"]
            if item["had_target"]:
                os.replace(target, item["backup"])
            os.replace(item["temporary"], target)
            item["installed"] = True
    except Exception:
        for item in reversed(prepared):
            target = item["target"]
            backup = item["backup"]
            if item["installed"]:
                _remove_file(target)
            if backup.exists():
                os.replace(backup, target)
            _remove_file(item["temporary"])
        raise
    else:
        for item in prepared:
            _remove_file(item["backup"])


class FilesFormatter:
    format_name = "files"
    supported_build_types = frozenset({"rust", "web"})

    def materialize(
        self,
        project: BuckyProject,
        module_key: str,
        result: BuildResult,
        install_references: List[InstallReference],
    ) -> List[MaterializedArtifact]:
        if result.build_type == "rust":
            return self._materialize_rust(project, module_key, result, install_references)
        if result.build_type == "web":
            return self._materialize_web(module_key, result, install_references)
        raise ValueError(
            f"Formatter files does not support builder type {result.build_type} for module {module_key}"
        )

    def _materialize_rust(
        self,
        project: BuckyProject,
        module_key: str,
        result: BuildResult,
        install_references: List[InstallReference],
    ) -> List[MaterializedArtifact]:
        module = project.modules[module_key]
        if not isinstance(module, RustModuleInfo):
            raise ValueError(f"Rust files formatter received non-Rust module {module_key}")
        artifacts = [artifact for artifact in result.artifacts if artifact.role == "executable"]
        if len(artifacts) != 1:
            raise ValueError(f"Rust module {module_key} must return exactly one executable artifact")
        artifact = artifacts[0]
        source = artifact.path
        if not source.is_file():
            raise FileNotFoundError(f"Rust executable artifact not found: {source}")

        records = []
        for reference in install_references:
            target = reference.staging_path
            if reference.install_path.endswith("/"):
                target = target / (artifact.install_name or module_key)
            target = Path(get_execute_name(target, source.suffix))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
            if artifact.executable:
                os.chmod(target, 0o755)
            records.append(
                MaterializedArtifact(
                    module_key=module_key,
                    build_type=result.build_type,
                    format=self.format_name,
                    source_path=source,
                    install_app=reference.app_name,
                    install_path=reference.install_path,
                    size=source.stat().st_size,
                )
            )
        return records

    def _materialize_web(
        self,
        module_key: str,
        result: BuildResult,
        install_references: List[InstallReference],
    ) -> List[MaterializedArtifact]:
        dist_dir = result.work_dir / "dist"
        if not dist_dir.is_dir():
            raise FileNotFoundError(
                f"Web files formatter requires a dist directory for module {module_key}: {dist_dir}"
            )
        records = []
        for reference in install_references:
            target = reference.staging_path
            if target.exists() or target.is_symlink():
                if not target.is_dir() or target.is_symlink():
                    raise ValueError(f"Web staging target must be a directory: {target}")
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dist_dir, target, copy_function=shutil.copyfile)
            records.append(
                MaterializedArtifact(
                    module_key=module_key,
                    build_type=result.build_type,
                    format=self.format_name,
                    source_path=dist_dir,
                    install_app=reference.app_name,
                    install_path=reference.install_path,
                )
            )
        return records


class PikgFormatter:
    format_name = "pikg"
    supported_build_types = None

    def materialize(
        self,
        project: BuckyProject,
        module_key: str,
        result: BuildResult,
        install_references: List[InstallReference],
    ) -> List[MaterializedArtifact]:
        module = project.modules[module_key]
        if not install_references:
            raise ValueError(f"PIKG module {module_key} has no app install reference")

        work_dir = result.work_dir.resolve()
        options = module.pikg or PikgModuleConfig()
        meta_dir = (work_dir / options.meta_dir).resolve()
        if not meta_dir.is_dir():
            raise FileNotFoundError(f"PIKG metadata directory not found: {meta_dir}")

        app = _read_json_object(meta_dir / "app.json", "app.json")
        pikg = _read_json_object(meta_dir / "pikg.json", "pikg.json")
        app_did = _require_string(app, "did", "app.json")
        app_version = _require_string(app, "version", "app.json")
        output_dir = pikg.get("output_dir", "../dapp_dist")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("pikg.json.output_dir must be a non-empty string")
        pikg_file = _require_string(pikg, "pikg_file", "pikg.json")
        if PurePosixPath(pikg_file).name != pikg_file or not pikg_file.endswith(".pikg"):
            raise ValueError(f"pikg.json.pikg_file must be a .pikg basename: {pikg_file}")
        for reference in install_references:
            if PurePosixPath(reference.install_path.replace("\\", "/")).name != pikg_file:
                raise ValueError(
                    f"PIKG filename mismatch for {module_key}: metadata={pikg_file}, "
                    f"app {reference.app_name}={reference.install_path}"
                )

        sources = _metadata_sources(meta_dir, pikg)
        build_argv = _buckyos_command()
        for source in sources:
            build_argv.extend(["--allow-read", str(source)])
        build_argv.extend(["--output", "json", "pikg", "build", str(meta_dir)])
        build_data = _run_buckyos_json(build_argv, work_dir)
        dist_dir = _resolve_cli_path(
            _require_string(build_data, "dist_dir", "pikg build data"),
            work_dir,
        )
        expected_dist = (meta_dir / output_dir).resolve()
        if dist_dir != expected_dist:
            raise ValueError(
                f"PIKG build dist_dir mismatch for {module_key}: {dist_dir} != {expected_dist}"
            )
        if build_data.get("ready_for_pack") is not True:
            raise ValueError(f"PIKG build did not report ready_for_pack for {module_key}")
        build_app_doc_id = _require_string(
            build_data,
            "app_doc_object_id",
            "pikg build data",
        )

        pack_data = _run_buckyos_json(
            [*_buckyos_command(), "--output", "json", "pikg", "pack", str(dist_dir)],
            work_dir,
        )
        if pack_data.get("validation") != "passed":
            raise ValueError(f"PIKG pack did not report validation=passed for {module_key}")
        pack_dist_dir = _resolve_cli_path(
            _require_string(pack_data, "dist_dir", "pikg pack data"),
            work_dir,
        )
        if pack_dist_dir != dist_dir:
            raise ValueError(f"PIKG pack dist_dir mismatch for {module_key}")
        raw_pikg_path = Path(_require_string(pack_data, "pikg_path", "pikg pack data"))
        if not raw_pikg_path.is_absolute():
            raw_pikg_path = work_dir / raw_pikg_path
        if raw_pikg_path.is_symlink():
            raise ValueError(f"PIKG output must not be a symbolic link: {raw_pikg_path}")
        pikg_path = raw_pikg_path.resolve()
        if not pikg_path.is_file() or pikg_path.parent != dist_dir or pikg_path.name != pikg_file:
            raise ValueError(f"PIKG pack returned an unexpected output path: {pikg_path}")

        pack_size = _require_integer(pack_data, "size", "pikg pack data")
        pack_digest = _require_string(pack_data, "pikg_digest", "pikg pack data")
        if not _SHA256.fullmatch(pack_digest):
            raise ValueError(f"PIKG pack returned an invalid pikg_digest: {pack_digest}")
        pack_app_doc_id = _require_string(
            pack_data,
            "app_doc_object_id",
            "pikg pack data",
        )
        if pack_size == 0 or pikg_path.stat().st_size != pack_size or _sha256(pikg_path) != pack_digest:
            raise ValueError(f"PIKG pack size or digest mismatch for {module_key}")

        info_data = _run_buckyos_json(
            [*_buckyos_command(), "--output", "json", "pikg", "info", str(pikg_path)],
            work_dir,
        )
        if info_data.get("schema_version") != 1 or info_data.get("valid") is not True:
            raise ValueError(f"PIKG info did not validate {module_key}")
        info_path = _resolve_cli_path(
            _require_string(info_data, "pikg_path", "pikg info data"),
            work_dir,
        )
        info_size = _require_integer(info_data, "size", "pikg info data")
        info_digest = _require_string(info_data, "pikg_digest", "pikg info data")
        info_app = info_data.get("app")
        if not isinstance(info_app, dict):
            raise ValueError("pikg info data.app must be an object")
        info_app_doc_id = _require_string(
            info_app,
            "app_doc_object_id",
            "pikg info data.app",
        )
        if (
            info_path != pikg_path
            or info_size != pack_size
            or info_digest != pack_digest
            or build_app_doc_id != pack_app_doc_id
            or pack_app_doc_id != info_app_doc_id
            or _require_string(info_app, "did", "pikg info data.app") != app_did
            or _require_string(info_app, "version", "pikg info data.app") != app_version
        ):
            raise ValueError(f"PIKG build/pack/info results disagree for {module_key}")

        _transactional_install(
            pikg_path,
            [reference.staging_path for reference in install_references],
            pack_size,
            pack_digest,
        )
        return [
            MaterializedArtifact(
                module_key=module_key,
                build_type=result.build_type,
                format=self.format_name,
                source_path=pikg_path,
                install_app=reference.app_name,
                install_path=reference.install_path,
                size=pack_size,
                digest=pack_digest,
            )
            for reference in install_references
        ]
