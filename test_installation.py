#!/usr/bin/env python3
"""
简单的测试脚本，用于验证 buckyos-devkit 安装是否成功
"""

def test_import():
    """测试模块导入"""
    print("测试模块导入...")
    try:
        import buckyos_devkit
        print(f"✓ 成功导入 buckyos_devkit, 版本: {buckyos_devkit.__version__}")
        
        from buckyos_devkit import util
        print("✓ 成功导入 util 模块")
        
        from buckyos_devkit import build
        print("✓ 成功导入 build 模块")
        
        from buckyos_devkit import install
        print("✓ 成功导入 install 模块")
        
        from buckyos_devkit.remote import Workspace
        print("✓ 成功导入 remote.Workspace")
        
        return True
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        return False

def test_util_functions():
    """测试 util 模块的基本功能"""
    print("\n测试 util 模块功能...")
    try:
        from buckyos_devkit import util
        
        # 测试获取 BuckyOS 根目录
        root = util.get_buckyos_root()
        print(f"✓ get_buckyos_root() = {root}")
        
        # 测试端口检查（测试一个不太可能被占用的端口）
        port_available = not util.check_port(65432)
        print(f"✓ check_port(65432) = {port_available}")
        
        # 测试获取系统编码
        encoding = util.get_system_encoding()
        print(f"✓ get_system_encoding() = {encoding}")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

def test_cli_commands():
    """测试命令行工具是否可用"""
    print("\n测试命令行工具...")
    import subprocess
    import sys
    
    commands = [
        "buckyos-build",
        "buckyos-install",
        "buckyos-remote"
    ]
    
    all_passed = True
    for cmd in commands:
        try:
            # 尝试运行 --help
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "buckyos-devkit"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✓ 包已安装，命令 {cmd} 应该可用")
            else:
                print(f"⚠ 包可能未正确安装")
                all_passed = False
        except Exception as e:
            print(f"✗ 检查命令 {cmd} 时出错: {e}")
            all_passed = False
    
    return all_passed

def main():
    """运行所有测试"""
    print("=" * 60)
    print("BuckyOS DevKit 安装验证")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(("模块导入", test_import()))
    results.append(("工具函数", test_util_functions()))
    results.append(("命令行工具", test_cli_commands()))
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✓ 所有测试通过！安装成功！")
        return 0
    else:
        print("✗ 部分测试失败，请检查安装")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())

