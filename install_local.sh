#!/bin/bash

# BuckyOS DevKit 本地安装脚本
# 使用方法: bash install_local.sh

set -e  # 遇到错误立即退出

echo "================================================"
echo "BuckyOS DevKit 本地安装"
echo "================================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "✓ 当前目录: $SCRIPT_DIR"
echo ""

# 检查虚拟环境
VENV_DIR="$SCRIPT_DIR/test_devkit"

if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo "✓ 虚拟环境创建完成"
    echo ""
fi

echo "激活虚拟环境..."
source "$VENV_DIR/bin/activate"
echo "✓ 虚拟环境已激活"
echo ""

# 显示 Python 路径
echo "Python 路径:"
which python3
which pip3
echo ""

# 升级 pip
echo "升级 pip..."
pip3 install --upgrade pip setuptools wheel
echo "✓ pip 升级完成"
echo ""

# 安装包
echo "安装 buckyos-devkit..."
pip3 install -e .
echo "✓ buckyos-devkit 安装完成"
echo ""

# 验证安装
echo "================================================"
echo "验证安装"
echo "================================================"
echo ""

# 检查包
echo "检查已安装的包:"
pip3 list | grep buckyos-devkit || echo "⚠️ 包未找到"
echo ""

# 测试导入
echo "测试模块导入:"
python3 -c "from buckyos_devkit import util; print('✓ 导入成功！')" || echo "✗ 导入失败"
echo ""

# 测试命令
echo "测试命令行工具:"
if command -v buckyos-build &> /dev/null; then
    echo "✓ buckyos-build 可用"
else
    echo "⚠️ buckyos-build 未找到（但可能已正确安装）"
fi

if command -v buckyos-install &> /dev/null; then
    echo "✓ buckyos-install 可用"
else
    echo "⚠️ buckyos-install 未找到（但可能已正确安装）"
fi

if command -v buckyos-remote &> /dev/null; then
    echo "✓ buckyos-remote 可用"
else
    echo "⚠️ buckyos-remote 未找到（但可能已正确安装）"
fi
echo ""

# 运行完整测试
echo "================================================"
echo "运行完整测试"
echo "================================================"
echo ""

if [ -f "test_installation.py" ]; then
    python3 test_installation.py
else
    echo "⚠️ test_installation.py 未找到，跳过测试"
fi

echo ""
echo "================================================"
echo "安装完成！"
echo "================================================"
echo ""
echo "使用方法:"
echo "  1. 激活虚拟环境: source test_devkit/bin/activate"
echo "  2. 使用命令: buckyos-build --help"
echo "  3. 退出环境: deactivate"
echo ""

