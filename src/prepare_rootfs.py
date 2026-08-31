from pathlib import Path
from typing import Optional

from .build_rust import _rust_build_result
from .formatters import FilesFormatter
from .module_build import BuildResult, collect_install_references
from .project import BuckyProject, RustModuleInfo, WebModuleInfo


_files_formatter = FilesFormatter()


def copy_rust_module(
    project: BuckyProject,
    module_name: str,
    rust_target: Optional[str] = None,
):
    module_info = project.modules.get(module_name)
    if not isinstance(module_info, RustModuleInfo):
        raise ValueError(f"Rust module {module_name} not found")
    result = _rust_build_result(project, module_name, rust_target or "")
    return _files_formatter.materialize(
        project,
        module_name,
        result,
        collect_install_references(project, module_name),
    )


def copy_web_module(project: BuckyProject, module_name: str):
    module_info = project.modules.get(module_name)
    if not isinstance(module_info, WebModuleInfo):
        raise ValueError(f"Web module {module_name} not found")
    result = BuildResult(
        module_key=module_name,
        build_type="web",
        work_dir=project.resolve_from_base_dir(module_info.src_dir).resolve(),
    )
    return _files_formatter.materialize(
        project,
        module_name,
        result,
        collect_install_references(project, module_name),
    )


def copy_build_results(
    project: BuckyProject,
    skip_web_module: bool,
    rust_target: Optional[str] = None,
    selected_modules: list[str] | None = None,
):
    print("🚀 Copying build result ...")
    records = []
    for module_name, module_info in project.modules.items():
        if selected_modules is not None and module_name not in selected_modules:
            continue
        if module_info.format != "files":
            continue
        if isinstance(module_info, RustModuleInfo):
            records.extend(copy_rust_module(project, module_name, rust_target))
        elif isinstance(module_info, WebModuleInfo) and not skip_web_module:
            records.extend(copy_web_module(project, module_name))
        elif not isinstance(module_info, WebModuleInfo):
            raise ValueError(f"Unsupported module type for files formatter: {type(module_info).__name__}")
    print("✅ Copy build result completed!")
    return records
