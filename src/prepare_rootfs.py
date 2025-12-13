import os
import shutil
import platform
from typing import Optional
from project import WebAppInfo, RustAppInfo, BuckyProject
from buckyos_kit import get_execute_name

_system_name = platform.system()

def copy_rust_app(project: BuckyProject, app_name:str):
    app_info: Optional[RustAppInfo] = project.apps[app_name]
    if not app_info:
        raise ValueError(f"Rust app {app_name} not found")
    if not isinstance(app_info, RustAppInfo):
        raise ValueError(f"Rust app {app_name} is not a RustAppInfo")

    src_file = os.path.join(project.rust_target_dir, "release", app_name)
    src_file = get_execute_name(src_file)
    for target_dir in app_info.target_dir:
        real_target = os.path.join(project.base_dir, target_dir, app_name)
        real_target = get_execute_name(real_target)
        
        print(f'+ Copying rust app: {src_file} => {real_target}')
        shutil.copy(src_file, real_target)

def copy_web_app(project: BuckyProject, app_name: str):
    app_info: Optional[WebAppInfo] = project.apps[app_name]
    if not app_info:
        raise ValueError(f"Web app {app_name} not found")
    if not isinstance(app_info, WebAppInfo):
        raise ValueError(f"Web app {app_name} is not a WebAppInfo")

    dist_dir = os.path.join(project.base_dir, app_info.src_dir, "dist")
    for target_dir in app_info.target_dir:
        real_target_dir = os.path.join(project.base_dir, target_dir)
        os.makedirs(real_target_dir, exist_ok=True)
        if os.path.exists(real_target_dir):
            print(f'- Removing existing directory: {real_target_dir}')
            shutil.rmtree(real_target_dir)
        print(f'+ Copying web app dist: {dist_dir} => {real_target_dir}')
        shutil.copytree(dist_dir, real_target_dir, copy_function=shutil.copyfile)

def copy_build_results(project: BuckyProject,skip_web_app:bool):
    print("🚀 Copying build result ...")
    for app_name, app_info in project.apps.items():
        if isinstance(app_info, RustAppInfo):
            copy_rust_app(project, app_name)
        elif isinstance(app_info, WebAppInfo):
            if not skip_web_app:
                copy_web_app(project, app_name)
        else:
            raise ValueError(f"App {app_name} is not a RustAppInfo or WebAppInfo")

    print("✅ Copy build result completed!")


