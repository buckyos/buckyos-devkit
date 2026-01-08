# buckyos-devkit

buckyos-devkit 是 BuckyOS 共用的开发脚本基础库。支持用如下方法使用：

## 快速开始

### 安装

**从 GitHub 安装**（项目发布后）:

```bash
pip install --force-reinstall "buckyos-devkit @ git+https://github.com/buckyos/buckyos-devkit.git"
```
> 📝 `--force-reinstall` 首次安装也可以使用，避免缓存导致 buckyos-devkit 版本未更新。

**本地开发安装**（当前推荐）:

```bash
# 1. 创建并激活虚拟环境
cd /Users/liuzhicong/project/buckyos-devkit
python3 -m venv test_devkit
source test_devkit/bin/activate

# 2. 安装包（可编辑模式）
pip3 install -e .

# 3. 验证安装
python3 test_installation.py
```

> 📝 详细的本地安装步骤和故障排除，请参考 [LOCAL_INSTALL.md](./LOCAL_INSTALL.md)

### 命令行工具

安装后会提供以下命令行工具：

- `buckyos-build` - 构建工具
- `buckyos-install` - 安装工具
- `buckyos-remote` - 远程管理工具

### 在代码中使用

```python
from buckyos_devkit import util

# 使用工具函数
root = util.get_buckyos_root()
util.check_process_exists("/path/to/process")
```

## 详细文档

更多使用示例和详细说明，请参考 [USAGE_EXAMPLE.md](./USAGE_EXAMPLE.md)

## 功能特性

- 🔨 **构建工具**: 支持多平台构建（Linux、Windows、macOS）
- 📦 **安装工具**: 自动化安装和配置
- 🌐 **远程管理**: 虚拟机和远程设备管理
- 🛠️ **工具函数**: 进程管理、端口检查等实用工具

## 依赖

- Python >= 3.8
- PyYAML >= 6.0
- Paramiko >= 3.0.0
- Requests >= 2.28.0
