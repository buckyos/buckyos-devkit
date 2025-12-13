#!/usr/bin/env python3
"""
使用真实的 build.py 和 install.py 功能进行测试
步骤：
1. 准备 mock 构建产物（模拟 Rust 编译和 Web 构建的输出）
2. 调用真实的 copy_build_results 函数
3. 调用真实的 install 相关函数
"""
import sys
import os
from pathlib import Path
import shutil

# 添加项目根目录到 Python 路径
devkit_root = Path(__file__).parent.parent
sys.path.insert(0, str(devkit_root))

from src.project import BuckyProject, WebModuleInfo, RustModuleInfo
from src.prepare_rootfs import copy_build_results
from src.install import update_app, install_app_data, clean_app

def prepare_mock_rust_build(project: BuckyProject):
    """准备模拟的 Rust 构建产物"""
    print("\n" + "=" * 70)
    print("步骤 1: 准备模拟的 Rust 构建产物")
    print("=" * 70)
    
    release_dir = project.base_dir / project.rust_target_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    
    for module_name, module_info in project.modules.items():
        if isinstance(module_info, RustModuleInfo):
            # 创建模拟的可执行文件
            exe_path = release_dir / module_name
            exe_content = f"""#!/bin/bash
# Mock Rust executable: {module_name}
echo "Running {module_name} (mock version)"
echo "Version: 1.0.0-test"
"""
            exe_path.write_text(exe_content)
            exe_path.chmod(0o755)
            print(f"  ✅ 创建模拟可执行文件: {exe_path}")

def prepare_mock_web_build(project: BuckyProject):
    """准备模拟的 Web 构建产物"""
    print("\n" + "=" * 70)
    print("步骤 2: 准备模拟的 Web 构建产物")
    print("=" * 70)
    
    for module_name, module_info in project.modules.items():
        if isinstance(module_info, WebModuleInfo):
            dist_dir = project.base_dir / module_info.src_dir / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建模拟的 Web 文件
            index_html = dist_dir / "index.html"
            index_html.write_text(f"""<!DOCTYPE html>
<html>
<head>
    <title>{module_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #333; }}
        .info {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Web Module: {module_name}</h1>
        <div class="info">
            <p><strong>Status:</strong> Running (Mock Build)</p>
            <p><strong>Version:</strong> 1.0.0-test</p>
            <p><strong>Build Time:</strong> Mock Build</p>
        </div>
    </div>
</body>
</html>
""")
            
            # 创建 app.js
            app_js = dist_dir / "app.js"
            app_js.write_text(f"""
console.log("Module {module_name} loaded");
console.log("This is a mock build");
""")
            
            print(f"  ✅ 创建模拟 Web 文件: {dist_dir}")

def test_copy_build_results(project: BuckyProject):
    """测试真实的 copy_build_results 函数"""
    print("\n" + "=" * 70)
    print("步骤 3: 调用真实的 copy_build_results 函数")
    print("=" * 70)
    
    try:
        # 调用真实的复制函数
        copy_build_results(project, skip_web_module=False)
        print("\n  ✅ copy_build_results 执行成功")
        return True
    except Exception as e:
        print(f"\n  ❌ copy_build_results 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_install_app(project: BuckyProject, app_name: str):
    """测试真实的安装功能"""
    print("\n" + "=" * 70)
    print(f"步骤 4: 测试安装应用 {app_name}")
    print("=" * 70)
    
    try:
        # 设置测试安装目录（不使用系统目录）
        test_install_root = project.base_dir / "test_install"
        app_info = project.apps[app_name]
        test_target = test_install_root / app_name
        
        print(f"  测试安装目录: {test_target}")
        
        # 先清理旧的安装
        if test_target.exists():
            print(f"  清理旧安装...")
            clean_app(project, app_name, test_target)
        
        # 调用真实的更新函数（复制模块）
        print(f"  安装模块...")
        update_app(project, app_name, test_target)
        
        # 安装数据目录
        print(f"  安装数据目录...")
        install_app_data(project, app_name, test_target)
        
        print(f"\n  ✅ 应用 {app_name} 安装成功")
        return True
    except Exception as e:
        print(f"\n  ❌ 应用安装失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_results(project: BuckyProject):
    """验证构建和安装结果"""
    print("\n" + "=" * 70)
    print("步骤 5: 验证结果")
    print("=" * 70)
    
    all_ok = True
    
    # 验证 rootfs 目录
    print("\n📁 验证 Rootfs 目录:")
    for app_name, app_info in project.apps.items():
        rootfs_path = project.base_dir / app_info.rootfs
        print(f"\n  应用: {app_name}")
        print(f"  路径: {rootfs_path}")
        
        if not rootfs_path.exists():
            print(f"    ❌ Rootfs 目录不存在")
            all_ok = False
            continue
        
        # 检查每个模块
        for module_name, module_path in app_info.modules.items():
            full_path = rootfs_path / module_path
            module_info = project.modules[module_name]
            
            if isinstance(module_info, RustModuleInfo):
                # Rust 模块应该是可执行文件
                exe_path = full_path / module_name
                if exe_path.exists() and exe_path.is_file():
                    print(f"    ✅ Rust 模块 {module_name}: {exe_path}")
                else:
                    print(f"    ❌ Rust 模块 {module_name} 未找到: {exe_path}")
                    all_ok = False
                    
            elif isinstance(module_info, WebModuleInfo):
                # Web 模块应该是目录
                if full_path.exists() and full_path.is_dir():
                    files = list(full_path.glob('*'))
                    print(f"    ✅ Web 模块 {module_name}: {full_path} ({len(files)} 文件)")
                else:
                    print(f"    ❌ Web 模块 {module_name} 未找到: {full_path}")
                    all_ok = False
    
    # 验证测试安装目录
    print("\n📦 验证测试安装目录:")
    test_install_root = project.base_dir / "test_install"
    if test_install_root.exists():
        print(f"  ✅ 测试安装目录存在: {test_install_root}")
        for app_name in project.apps.keys():
            app_path = test_install_root / app_name
            if app_path.exists():
                print(f"    ✅ 应用 {app_name} 已安装")
            else:
                print(f"    ❌ 应用 {app_name} 未安装")
                all_ok = False
    else:
        print(f"  ⚠️  测试安装目录不存在（可能未运行安装测试）")
    
    return all_ok

def show_directory_tree(project: BuckyProject):
    """显示目录结构"""
    print("\n" + "=" * 70)
    print("目录结构")
    print("=" * 70)
    
    def print_tree(path: Path, prefix: str = "", max_depth: int = 4, current_depth: int = 0):
        if current_depth >= max_depth:
            return
        
        if not path.exists():
            return
        
        try:
            items = sorted(path.iterdir())
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = "    " if is_last else "│   "
                
                if item.is_file():
                    size = item.stat().st_size
                    print(f"{prefix}{current_prefix}{item.name} ({size} bytes)")
                else:
                    print(f"{prefix}{current_prefix}{item.name}/")
                    print_tree(item, prefix + next_prefix, max_depth, current_depth + 1)
        except PermissionError:
            pass
    
    # 显示 rootfs 目录
    print("\n📂 Rootfs 目录:")
    for app_name, app_info in project.apps.items():
        rootfs_path = project.base_dir / app_info.rootfs
        print(f"\n{app_name}/ ({rootfs_path})")
        print_tree(rootfs_path, "  ")
    
    # 显示测试安装目录
    test_install_root = project.base_dir / "test_install"
    if test_install_root.exists():
        print(f"\n📂 测试安装目录:")
        print(f"test_install/ ({test_install_root})")
        print_tree(test_install_root, "  ")

def main():
    print("=" * 70)
    print("真实构建和安装功能测试")
    print("=" * 70)
    
    # 加载配置
    config_path = Path(__file__).parent / 'bucky_project.json'
    print(f"\n📖 加载配置文件: {config_path}")
    project = BuckyProject.from_file(config_path)
    project.base_dir = Path(__file__).parent  # 设置为测试项目目录
    print(f"  ✅ 项目: {project.name}")
    
    # 步骤 1: 准备 Rust 构建产物
    prepare_mock_rust_build(project)
    
    # 步骤 2: 准备 Web 构建产物
    prepare_mock_web_build(project)
    
    # 步骤 3: 调用真实的 copy_build_results
    if not test_copy_build_results(project):
        print("\n❌ 测试失败，停止执行")
        return 1
    
    # 步骤 4: 测试安装功能
    for app_name in project.apps.keys():
        if not test_install_app(project, app_name):
            print(f"\n⚠️  应用 {app_name} 安装测试失败")
    
    # 步骤 5: 验证结果
    success = verify_results(project)
    
    # 显示目录结构
    show_directory_tree(project)
    
    # 总结
    print("\n" + "=" * 70)
    if success:
        print("✅ 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查上面的错误信息")
    print("=" * 70)
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())

