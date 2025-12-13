#!/usr/bin/env python3
"""
模拟构建流程测试脚本（不依赖真实的 Rust/Web 构建工具）
"""
import sys
import os
from pathlib import Path
import shutil

# 添加 src 目录到 Python 路径
devkit_root = Path(__file__).parent.parent
sys.path.insert(0, str(devkit_root / 'src'))

from project import BuckyProject, WebModuleInfo, RustModuleInfo

def mock_build_rust_module(project: BuckyProject, module_name: str):
    """模拟 Rust 模块构建"""
    print(f"\n🦀 模拟构建 Rust 模块: {module_name}")
    
    # 创建模拟的 Rust 构建产物
    release_dir = project.base_dir / project.rust_target_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建一个简单的可执行文件
    exe_path = release_dir / module_name
    exe_path.write_text("#!/bin/bash\necho 'Mock executable: {}'\n".format(module_name))
    exe_path.chmod(0o755)
    
    print(f"   ✅ 已创建模拟可执行文件: {exe_path}")

def mock_copy_module(project: BuckyProject, module_name: str, module_info):
    """模拟复制模块到应用目录"""
    print(f"\n📦 复制模块: {module_name}")
    
    for app_name, app_info in project.apps.items():
        if module_name not in app_info.modules:
            continue
        
        module_path = app_info.modules[module_name]
        print(f"   复制到应用: {app_name}")
        
        if isinstance(module_info, RustModuleInfo):
            # 复制 Rust 可执行文件
            src_file = project.base_dir / project.rust_target_dir / "release" / module_name
            target_file = project.base_dir / app_info.rootfs / module_path / module_name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, target_file)
            target_file.chmod(0o755)
            print(f"      ✅ Rust 可执行文件: {target_file}")
            
        elif isinstance(module_info, WebModuleInfo):
            # 复制 Web 文件
            src_dir = project.base_dir / module_info.src_dir / "dist"
            target_dir = project.base_dir / app_info.rootfs / module_path
            
            if target_dir.exists():
                shutil.rmtree(target_dir)
            
            shutil.copytree(src_dir, target_dir)
            print(f"      ✅ Web 文件: {target_dir}")

def main():
    print("=" * 70)
    print("模拟构建流程测试")
    print("=" * 70)
    
    # 加载配置
    config_path = Path(__file__).parent / 'bucky_project.json'
    print(f"\n1. 加载配置文件: {config_path}")
    project = BuckyProject.from_file(config_path)
    project.base_dir = Path(__file__).parent
    print(f"   ✅ 项目: {project.name}")
    
    # 模拟构建所有 Rust 模块
    print("\n2. 构建 Rust 模块:")
    for name, info in project.modules.items():
        if isinstance(info, RustModuleInfo):
            mock_build_rust_module(project, name)
    
    # 复制所有模块到应用目录
    print("\n3. 复制模块到应用目录:")
    for name, info in project.modules.items():
        mock_copy_module(project, name, info)
    
    # 显示结果
    print("\n4. 构建结果:")
    for app_name, app_info in project.apps.items():
        rootfs_path = project.base_dir / app_info.rootfs
        print(f"\n   应用: {app_name}")
        print(f"   Rootfs 目录: {rootfs_path}")
        
        if rootfs_path.exists():
            print(f"   目录结构:")
            for root, dirs, files in os.walk(rootfs_path):
                level = root.replace(str(rootfs_path), '').count(os.sep)
                indent = ' ' * 2 * level
                print(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * 2 * (level + 1)
                for file in files:
                    file_path = Path(root) / file
                    size = file_path.stat().st_size
                    print(f"{subindent}{file} ({size} bytes)")
    
    print("\n" + "=" * 70)
    print("✅ 模拟构建测试完成!")
    print("=" * 70)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

