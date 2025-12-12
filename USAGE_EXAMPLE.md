# BuckyOS DevKit 使用示例

## 安装

### 从 GitHub 安装

```bash
pip install "buckyos-devkit @ git+https://github.com/buckyos/bucky-devkit.git"
```

### 本地开发安装

```bash
# 克隆仓库
git clone https://github.com/buckyos/bucky-devkit.git
cd bucky-devkit

# 可编辑模式安装
pip install -e .

# 或安装开发依赖
pip install -e ".[dev]"
```

## 命令行工具使用

安装完成后，你可以使用以下命令行工具：

### 1. buckyos-build - 构建工具

```bash
# 基本构建
buckyos-build

# 不构建 web apps
buckyos-build --no-build-web-apps

# 不安装
buckyos-build --no-install

# 指定目标平台
buckyos-build --target=x86_64-unknown-linux-musl

# 构建 amd64 版本
buckyos-build amd64

# 构建 aarch64 版本
buckyos-build aarch64

# 包含 tray controller
buckyos-build --tray-controller

# Windows 自动 SDK
buckyos-build --auto-win-sdk
```

### 2. buckyos-install - 安装工具

```bash
# 安装到默认位置
buckyos-install

# 完整安装（包括所有文件）
buckyos-install --all
```

默认安装位置：
- Linux: `/opt/buckyos`
- Windows: `%APPDATA%\buckyos`
- macOS: 根据 `BUCKYOS_ROOT` 环境变量

### 3. buckyos-remote - 远程管理工具

```bash
# 创建虚拟机
buckyos-remote <group_name> create_vms

# 查看虚拟机信息
buckyos-remote <group_name> info_vms

# 启动虚拟机
buckyos-remote <group_name> start_vms

# 停止虚拟机
buckyos-remote <group_name> stop_vms

# 清理虚拟机
buckyos-remote <group_name> clean_vms

# 创建快照
buckyos-remote <group_name> snapshot <snapshot_name>

# 恢复快照
buckyos-remote <group_name> restore <snapshot_name>

# 安装应用到所有设备
buckyos-remote <group_name> install

# 安装应用到指定设备
buckyos-remote <group_name> install <device_id>

# 安装指定应用
buckyos-remote <group_name> install <device_id> --apps app1 app2

# 更新应用
buckyos-remote <group_name> update <device_id> --apps app1 app2

# 启动 buckyos
buckyos-remote <group_name> start

# 停止 buckyos
buckyos-remote <group_name> stop

# 收集日志
buckyos-remote <group_name> clog

# 在节点上执行命令
buckyos-remote <group_name> run <node_id> <command>
```

## 在 Python 代码中使用

### 使用工具函数

```python
from buckyos_devkit import util

# 检查进程是否存在
if util.check_process_exists("/path/to/process"):
    print("进程正在运行")

# 检查端口是否可用
if util.check_port(8080):
    print("端口 8080 已被占用")

# 杀死进程
util.kill_process("process_name")

# 后台启动进程
util.nohup_start("your_command", env_vars={"KEY": "VALUE"})

# 获取 BuckyOS 根目录
root = util.get_buckyos_root()
print(f"BuckyOS 根目录: {root}")

# 获取用户数据目录
user_dir = util.get_user_data_dir("user_id")

# 获取应用数据目录
app_dir = util.get_app_data_dir("app_id", "owner_user_id")

# 确保目录可访问
util.ensure_directory_accessible("/path/to/dir")
```

### 使用构建功能

```python
from buckyos_devkit.build import build

# 执行构建
build(
    skip_web_app=False,
    skip_install=False,
    target="x86_64-unknown-linux-musl",
    with_tray_controller=False,
    auto_win_sdk=False
)
```

### 使用安装功能

```python
from buckyos_devkit.install import install, install_apps, get_install_root_dir

# 获取安装目录
install_dir = get_install_root_dir()
print(f"安装目录: {install_dir}")

# 执行安装
install(install_all=True)

# 安装预装应用
install_apps()
```

### 使用远程管理

```python
from pathlib import Path
from buckyos_devkit.remote.worksapce import Workspace

# 创建工作空间
workspace_dir = Path("/path/to/workspace")
workspace = Workspace(workspace_dir)
workspace.load()

# 创建虚拟机
workspace.create_vms()

# 获取虚拟机信息
info = workspace.info_vms()
print(info)

# 安装应用
workspace.install("device_id", ["app1", "app2"])

# 启动服务
workspace.start()

# 停止服务
workspace.stop()
```

## 环境变量

- `BUCKYOS_ROOT`: BuckyOS 根目录位置
- `SUDO_USER`: 在 Linux 上用于设置数据目录权限

## 配置文件

远程管理工具需要在 `src/remote/dev_configs/<group_name>/` 目录下配置：

- `nodes.json`: 节点配置
- `vm_config.json`: 虚拟机配置  
- `apps/`: 应用配置目录
- `templates/`: 模板配置目录

## 注意事项

1. 在 Windows 上运行某些功能可能需要管理员权限
2. 在 Linux 上安装到系统目录需要 sudo 权限
3. 远程管理工具依赖 Multipass 虚拟机管理工具
4. 构建 Rust 项目需要预先安装 Rust 工具链

