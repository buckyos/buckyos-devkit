# 🚀 BuckyOS DevKit 快速开始指南

## ✅ 成功安装！

您的 `buckyos-devkit` 已经成功安装并通过了所有测试！

## 📦 安装方法

### 方法 1: 本地开发安装（当前推荐）

```bash
# 1. 进入项目目录
cd /Users/liuzhicong/project/buckyos-devkit

# 2. 运行一键安装脚本
bash install_local.sh

# 3. 激活虚拟环境
source test_devkit/bin/activate
```

### 方法 2: 从 GitHub 安装（项目发布后）

```bash
pip install "buckyos-devkit @ git+https://github.com/buckyos/bucky-devkit.git"
```

## 🛠️ 可用的命令行工具

安装后，您可以使用以下三个命令行工具：

### 1. `buckyos-build` - 构建工具

**注意**: 此命令需要在实际的 BuckyOS 项目目录中运行，而不是在 devkit 目录中运行。

```bash
# 在 BuckyOS 项目目录中使用
cd /path/to/buckyos-project
buckyos-build

# 查看帮助
buckyos-build --help

# 常用选项
buckyos-build --no-build-web-modules  # 跳过 web modules 构建
buckyos-build --no-install            # 不安装
buckyos-build --target=x86_64-unknown-linux-musl  # 指定目标
buckyos-build --app demo_app          # 只构建指定 app 使用的模块
buckyos-build --app app1 app2         # 同时构建多个 app 使用的模块
buckyos-build --timings               # 生成 Cargo timings 报告
buckyos-build --timings-dir ./timings # 生成并复制 Cargo timings 报告
```

### 2. `buckyos-install` - 安装工具

```bash
# 安装到默认位置
buckyos-install

# 完整安装
buckyos-install --all
```

### 3. `buckyos-remote` - 远程管理工具

```bash
# 查看帮助
buckyos-remote --help

# 示例命令（需要配置文件）
buckyos-remote dev_group create_vms
buckyos-remote dev_group info_vms
buckyos-remote dev_group install device1 --apps app1 app2
buckyos-remote dev_group uninstall device1 --apps app1 app2
```

## 💻 在 Python 代码中使用

```python
# 导入并使用工具函数
from buckyos_devkit import util

# 获取 BuckyOS 根目录
root = util.get_buckyos_root()
print(f"BuckyOS 根目录: {root}")

# 检查进程是否运行
if util.check_process_exists("/path/to/process"):
    print("进程正在运行")

# 检查端口
if util.check_port(8080):
    print("端口 8080 已被占用")

# 后台启动进程
util.nohup_start("your_command", env_vars={"KEY": "VALUE"})
```

## 🧪 验证安装

```bash
# 激活虚拟环境
source test_devkit/bin/activate

# 运行测试脚本
python3 test_installation.py

# 应该看到:
# ✓ 所有测试通过！安装成功！
```

## 📝 测试结果

```
============================================================
BuckyOS DevKit 安装验证
============================================================
测试模块导入...
✓ 成功导入 buckyos_devkit, 版本: 0.1.0
✓ 成功导入 util 模块
✓ 成功导入 build 模块
✓ 成功导入 install 模块
✓ 成功导入 remote.Workspace

测试 util 模块功能...
✓ get_buckyos_root() = /opt/buckyos/
✓ check_port(65432) = True
✓ get_system_encoding() = utf-8

测试命令行工具...
✓ 包已安装，命令 buckyos-build 应该可用
✓ 包已安装，命令 buckyos-install 应该可用
✓ 包已安装，命令 buckyos-remote 应该可用

============================================================
测试总结
============================================================
模块导入: ✓ 通过
工具函数: ✓ 通过
命令行工具: ✓ 通过
============================================================
✓ 所有测试通过！安装成功！
```

## 📚 更多文档

- [README.md](./README.md) - 项目概览和快速开始
- [USAGE_EXAMPLE.md](./USAGE_EXAMPLE.md) - 详细的使用示例和 API 文档
- [LOCAL_INSTALL.md](./LOCAL_INSTALL.md) - 本地安装详细说明和故障排除

## 🔄 日常使用流程

### 在您的项目中使用 buckyos-devkit

```bash
# 1. 激活 buckyos-devkit 的虚拟环境
source /Users/liuzhicong/project/buckyos-devkit/test_devkit/bin/activate

# 2. 进入您的 BuckyOS 项目目录
cd /path/to/your/buckyos-project

# 3. 使用 devkit 命令
buckyos-build
buckyos-install
buckyos-remote dev_group info_vms

# 4. 完成后退出虚拟环境
deactivate
```

### 在其他 Python 项目中使用

```bash
# 在您的项目虚拟环境中安装
cd /path/to/your/project
source venv/bin/activate
pip install -e /Users/liuzhicong/project/buckyos-devkit

# 然后在代码中导入使用
python3 -c "from buckyos_devkit import util; print(util.get_buckyos_root())"
```

## ⚠️ 重要提示

1. **buckyos-build 命令**: 需要在包含 `kernel/node_active` 等源代码目录的 BuckyOS 项目中运行
2. **虚拟环境**: 建议始终在虚拟环境中使用，避免污染系统 Python
3. **权限问题**: 某些操作（如安装到系统目录）可能需要 sudo 权限

## 🆘 遇到问题？

如果遇到导入错误或命令找不到的问题：

```bash
# 1. 确保虚拟环境已激活
source test_devkit/bin/activate

# 2. 检查 python 路径
which python3  # 应该指向虚拟环境中的 python

# 3. 重新安装
pip3 uninstall buckyos-devkit -y
pip3 install -e .

# 4. 重新运行测试
python3 test_installation.py
```

## 🎉 下一步

现在您可以：

1. 在您的 BuckyOS 项目中使用这些工具
2. 查看 [USAGE_EXAMPLE.md](./USAGE_EXAMPLE.md) 了解更多使用方法
3. 将项目推送到 GitHub，让其他人也能使用
4. 根据需要扩展和自定义工具函数

祝您开发顺利！🚀
