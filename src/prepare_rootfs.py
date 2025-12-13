import os
import shutil
import platform
from typing import Optional
from project import WebModuleInfo, RustModuleInfo, BuckyProject
from buckyos_kit import get_execute_name

_system_name = platform.system()

def copy_rust_module(project: BuckyProject, module_name:str):
    module_info: Optional[RustModuleInfo] = project.modules[module_name]
    if not module_info:
        raise ValueError(f"Rust module {module_name} not found")
    if not isinstance(module_info, RustModuleInfo):
        raise ValueError(f"Rust module {module_name} is not a RustModuleInfo")

    for app_info in project.apps.values():
        module_path = app_info.modules[module_name]
        if module_path is None:
            continue
        print(f'* Copying rust modules to app {app_info.name}...')
        src_file = os.path.join(project.rust_target_dir, "release", module_name)
        src_file = get_execute_name(src_file)
        real_target = os.path.join(project.base_dir, app_info.rootfs, module_path)
        print(f'+ Copying rust executable: {src_file} => {real_target}')
        shutil.copy(src_file, real_target)


def copy_web_module(project: BuckyProject, module_name: str):
    module_info: Optional[WebModuleInfo] = project.modules[module_name]
    if not module_info:
        raise ValueError(f"Web module {module_name} not found")
    if not isinstance(module_info, WebModuleInfo):
        raise ValueError(f"Web module {module_name} is not a WebModuleInfo")

    dist_dir = os.path.join(project.base_dir, module_info.src_dir, "dist")

    for app_info in project.apps.values():
        module_path = app_info.modules[module_name]
        if module_path is None:
            continue
        
        print(f'* Copying web modules to app {app_info.name}...')
        real_target_dir = os.path.join(project.base_dir, app_info.rootfs, module_path)
        os.makedirs(real_target_dir, exist_ok=True)
        if os.path.exists(real_target_dir):
            print(f'- Removing existing directory: {real_target_dir}')
            shutil.rmtree(real_target_dir)
        print(f'+ Copying web module dist: {dist_dir} => {real_target_dir}')
        shutil.copytree(dist_dir, real_target_dir, copy_function=shutil.copyfile)


def copy_build_results(project: BuckyProject,skip_web_module:bool):
    print("🚀 Copying build result ...")
    for module_name, module_info in project.modules.items():
        if isinstance(module_info, RustModuleInfo):
            copy_rust_module(project, module_name)
        elif isinstance(module_info, WebModuleInfo):
            if not skip_web_module:
                copy_web_module(project, module_name)
        else:
            raise ValueError(f"Module {module_name} is not a RustModuleInfo or WebModuleInfo")

    print("✅ Copy build result completed!")


