# 本地安装测试指南

在将项目推送到 GitHub 之前，请使用以下步骤在本地测试安装。

## 方法 1: 使用虚拟环境安装（推荐）

### 步骤 1: 创建并激活虚拟环境

```bash
# 进入项目目录
cd /Users/liuzhicong/project/buckyos-devkit

# 创建虚拟环境（如果还没有）
python3 -m venv test_devkit

# 激活虚拟环境
source test_devkit/bin/activate

# 确认虚拟环境已激活（应该显示虚拟环境中的 python 路径）
which python3
which pip3
```

### 步骤 2: 升级 pip

```bash
pip3 install --upgrade pip setuptools wheel
```

### 步骤 3: 安装包（可编辑模式）

```bash
# 可编辑模式安装（代码修改会立即生效）
pip3 install -e .

# 或安装开发依赖
pip3 install -e ".[dev]"
```

### 步骤 4: 验证安装

```bash
# 检查包是否安装成功
pip3 list | grep buckyos-devkit

# 测试命令行工具
buckyos-build --help
buckyos-install --help
buckyos-remote --help

# 运行测试脚本
python3 test_installation.py
```

### 步骤 5: 测试导入

```bash
python3 -c "from buckyos_devkit import util; print(util.get_buckyos_root())"
```

## 方法 2: 直接从本地路径安装

如果您在另一个项目中想测试这个包：

```bash
# 激活目标项目的虚拟环境
cd /path/to/your/project
source venv/bin/activate

# 从本地路径安装
pip3 install -e /Users/liuzhicong/project/buckyos-devkit
```

## 方法 3: 构建并安装 wheel 文件

```bash
cd /Users/liuzhicong/project/buckyos-devkit

# 确保已安装 build 工具
pip3 install build

# 构建 wheel 文件
python3 -m build

# 安装生成的 wheel 文件
pip3 install dist/buckyos_devkit-0.1.0-py3-none-any.whl
```

## 常见问题

### Q1: 提示 "externally-managed-environment" 错误

**原因**: macOS 系统的 Python 被设置为外部管理，不允许直接安装包。

**解决方案**: 
1. 使用虚拟环境（推荐）
2. 或者使用 `--break-system-packages` 标志（不推荐）

### Q2: 虚拟环境没有正确激活

**检查方法**:
```bash
# 应该指向虚拟环境中的 python
which python3

# 正确的输出应该类似:
# /Users/liuzhicong/project/buckyos-devkit/test_devkit/bin/python3
```

**重新激活**:
```bash
deactivate  # 先退出当前环境
source test_devkit/bin/activate  # 重新激活
```

### Q3: 命令找不到

如果安装后命令找不到，检查：

```bash
# 查看安装的脚本位置
pip3 show -f buckyos-devkit | grep bin

# 确保虚拟环境的 bin 目录在 PATH 中
echo $PATH
```

## 推送到 GitHub 后

项目推送到 GitHub 后，其他用户可以这样安装：

```bash
# 从 GitHub 安装
pip install "buckyos-devkit @ git+https://github.com/buckyos/bucky-devkit.git"

# 从 GitHub 安装特定分支
pip install "buckyos-devkit @ git+https://github.com/buckyos/bucky-devkit.git@main"

# 从 GitHub 安装特定标签
pip install "buckyos-devkit @ git+https://github.com/buckyos/bucky-devkit.git@v0.1.0"
```

## 完整的测试流程示例

```bash
# 1. 进入项目目录
cd /Users/liuzhicong/project/buckyos-devkit

# 2. 创建虚拟环境（如果需要）
python3 -m venv test_devkit

# 3. 激活虚拟环境
source test_devkit/bin/activate

# 4. 升级 pip
pip3 install --upgrade pip

# 5. 安装包
pip3 install -e .

# 6. 验证安装
python3 test_installation.py

# 7. 测试命令
buckyos-build --help

# 8. 测试导入
python3 -c "from buckyos_devkit import util; print('导入成功！')"

# 9. 完成后退出虚拟环境
deactivate
```

## 清理

如果需要重新安装：

```bash
# 卸载包
pip3 uninstall buckyos-devkit -y

# 重新安装
pip3 install -e .

# 或者清理构建产物
rm -rf build/ dist/ *.egg-info
```

