import os
from pathlib import Path
import shutil
import platform
from typing import Optional
from .project import WebModuleInfo, RustModuleInfo, BuckyProject
from .buckyos_kit import get_execute_name
from .build_rust import is_cross_compile_target

_system_name = platform.system()

def copy_rust_module(project: BuckyProject, module_name: str, rust_target: Optional[str] = None):
    module_info: Optional[RustModuleInfo] = project.modules.get(module_name)
    if not module_info:
        raise ValueError(f"Rust module {module_name} not found")
    if not isinstance(module_info, RustModuleInfo):
        raise ValueError(f"Rust module {module_name} is not a RustModuleInfo")

    for app_info in project.apps.values():
        if module_name not in app_info.modules:
            continue
        module_path = app_info.modules[module_name]
        
        print(f'* Copying rust module to app {app_info.name}...')
        
        # 构建源文件路径
        # 当需要交叉编译时（get_cross_compile_env_vars_by_target 返回非 None），
        # cargo 会使用 --target 参数，编译结果会放在 {target_dir}/{target}/release/
        # 否则放在 {target_dir}/release/
        use_target_subdir = False
        if rust_target:
            use_target_subdir = is_cross_compile_target(rust_target)

        rust_target_dir = project.resolve_from_config(project.rust_target_dir)
        if use_target_subdir:
            src_file = rust_target_dir / rust_target / "release" / module_name
        else:
            src_file = rust_target_dir / "release" / module_name
        src_file = get_execute_name(src_file)
        
        # 目标路径：rootfs/module_path/module_name
        
        if not module_path.endswith("/"):
            real_target: Path = project.resolve_from_base_dir(app_info.rootfs) / module_path
        else:
            real_target: Path = project.resolve_from_base_dir(app_info.rootfs) / module_path / module_name

        os.makedirs(real_target.parent, exist_ok=True)
        real_target = get_execute_name(real_target)
        
        print(f'+ Copying rust executable: {src_file} => {real_target}')
        shutil.copy(src_file, real_target)
        # 确保可执行权限
        os.chmod(real_target, 0o755)


def copy_web_module(project: BuckyProject, module_name: str):
    module_info: Optional[WebModuleInfo] = project.modules.get(module_name)
    if not module_info:
        raise ValueError(f"Web module {module_name} not found")
    if not isinstance(module_info, WebModuleInfo):
        raise ValueError(f"Web module {module_name} is not a WebModuleInfo")

    dist_dir = project.resolve_from_base_dir(module_info.src_dir) / "dist"

    for app_info in project.apps.values():
        if module_name not in app_info.modules:
            continue
        module_path = app_info.modules[module_name]
        
        print(f'* Copying web module to app {app_info.name}...')
        real_target_dir = project.resolve_from_base_dir(app_info.rootfs) / module_path
        
        # 如果目标目录存在，先删除
        if os.path.exists(real_target_dir):
            print(f'- Removing existing directory: {real_target_dir}')
            shutil.rmtree(real_target_dir)
        
        print(f'+ Copying web module dist: {dist_dir} => {real_target_dir}')
        shutil.copytree(dist_dir, real_target_dir, copy_function=shutil.copyfile)


def copy_build_results(
    project: BuckyProject,
    skip_web_module: bool,
    rust_target: Optional[str] = None,
    selected_modules: list[str] | None = None,
):
    print("🚀 Copying build result ...")
    for module_name, module_info in project.modules.items():
        if selected_modules is not None and module_name not in selected_modules:
            continue
        if isinstance(module_info, RustModuleInfo):
            copy_rust_module(project, module_name, rust_target)
        elif isinstance(module_info, WebModuleInfo):
            if not skip_web_module:
                copy_web_module(project, module_name)
        else:
            raise ValueError(f"Module {module_name} is not a RustModuleInfo or WebModuleInfo")

    print("✅ Copy build result completed!")


