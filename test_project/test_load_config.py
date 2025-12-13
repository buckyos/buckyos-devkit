#!/usr/bin/env python3
"""
测试配置文件加载功能
"""
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
devkit_root = Path(__file__).parent.parent
sys.path.insert(0, str(devkit_root / 'src'))

from project import BuckyProject

def main():
    print("=" * 60)
    print("测试 BuckyProject 配置加载")
    print("=" * 60)
    
    # 加载配置文件
    config_path = Path(__file__).parent / 'bucky_project.json'
    print(f"\n1. 加载配置文件: {config_path}")
    
    try:
        project = BuckyProject.from_file(config_path)
        print("   ✅ 配置加载成功!")
    except Exception as e:
        print(f"   ❌ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 显示项目信息
    print(f"\n2. 项目信息:")
    print(f"   - 项目名称: {project.name}")
    print(f"   - 基础目录: {project.base_dir}")
    print(f"   - Rust 构建目录: {project.rust_target_dir}")
    
    # 显示模块信息
    print(f"\n3. 模块列表 ({len(project.modules)} 个):")
    for name, info in project.modules.items():
        print(f"   - {name}:")
        print(f"     类型: {type(info).__name__}")
        if hasattr(info, 'src_dir'):
            print(f"     源目录: {info.src_dir}")
    
    # 显示应用信息
    print(f"\n4. 应用列表 ({len(project.apps)} 个):")
    for name, info in project.apps.items():
        print(f"   - {name}:")
        print(f"     Rootfs: {info.rootfs}")
        print(f"     默认目标: {info.default_target_rootfs}")
        print(f"     包含模块: {list(info.modules.keys())}")
        if info.modules:
            for mod_name, mod_path in info.modules.items():
                print(f"       • {mod_name} -> {mod_path}")
    
    # 测试保存配置
    print(f"\n5. 测试保存配置:")
    output_path = Path(__file__).parent / 'bucky_project_test_output.json'
    try:
        project.save(output_path)
        print(f"   ✅ 配置已保存到: {output_path}")
    except Exception as e:
        print(f"   ❌ 保存失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    return 0

if __name__ == '__main__':
    sys.exit(main())

