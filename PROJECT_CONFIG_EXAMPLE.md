# BuckyProject 配置文件使用指南

## 📝 配置文件格式

`BuckyProject` 支持从 JSON 或 YAML 文件加载配置，让项目配置更加清晰和可维护。

## 🚀 快速开始

### 方式 1: 从 JSON 文件加载

```python
from buckyos_devkit.project import BuckyProject

# 从 JSON 文件加载
project = BuckyProject.from_file('buckyos.json')

# 使用加载的配置
print(f"项目名称: {project.name}")
print(f"模块数量: {len(project.modules)}")

# 构建项目
from buckyos_devkit.build_web_apps import build_web_modules
build_web_modules(project)
```

### 方式 2: 从 YAML 文件加载

```python
# 从 YAML 文件加载（需要安装 pyyaml）
project = BuckyProject.from_file('buckyos.yaml')
```

### 方式 3: 代码创建并保存

```python
from pathlib import Path
from buckyos_devkit.project import BuckyProject, WebModuleInfo, RustModuleInfo

# 在代码中创建项目
project = BuckyProject(
    name='my-project',
    base_dir=Path('/path/to/project')
)

# 添加模块
project.add_web_module('frontend', WebModuleInfo(
    name='frontend',
    src_dir=Path('web/frontend'),
    target_dir=[Path('rootfs/modules/frontend')]
))

project.add_rust_module('daemon', RustModuleInfo(
    name='daemon',
    target_dir=[Path('rootfs/bin')]
))

# 保存到文件
project.save('buckyos.json')  # 或 'buckyos.yaml'
```

## 📄 配置文件示例

### JSON 格式 (buckyos.json)

```json
{
  "name": "my-buckyos-project",
  "base_dir": "/path/to/your/project",
  "modules": {
    "node_active": {
      "type": "web",
      "name": "node_active",
      "src_dir": "kernel/node_active",
      "target_dir": ["rootfs/modules/node_active"]
    },
    "admin_panel": {
      "type": "web",
      "name": "admin_panel",
      "src_dir": "modules/admin",
      "target_dir": ["rootfs/modules/admin"]
    },
    "core_daemon": {
      "type": "rust",
      "name": "core_daemon",
      "target_dir": ["rootfs/bin"]
    }
  },
  "rust_env": {
    "RUSTFLAGS": "-C target-feature=+crt-static"
  }
}
```

### YAML 格式 (buckyos.yaml)

```yaml
name: my-buckyos-project
base_dir: /path/to/your/project

modules:
  node_active:
    type: web
    name: node_active
    src_dir: kernel/node_active
    target_dir:
      - rootfs/modules/node_active
  
  admin_panel:
    type: web
    name: admin_panel
    src_dir: modules/admin
    target_dir:
      - rootfs/modules/admin
  
  core_daemon:
    type: rust
    name: core_daemon
    target_dir:
      - rootfs/bin

rust_env:
  RUSTFLAGS: "-C target-feature=+crt-static"
```

## 🔧 配置字段说明

### 项目级别字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 项目名称 |
| `base_dir` | string | ❌ | 项目根目录（默认为当前目录） |
| `modules` | object | ❌ | 模块列表 |
| `rust_target_dir` | string | ❌ | Rust 构建输出目录 |
| `rust_env` | object | ❌ | Rust 编译环境变量 |

### 用户本地覆盖配置

`buckyos-build` 和 `buckyos-install` 会先加载团队共享的 `bucky_project.json` / `bucky_project.yaml` / `bucky_project.yml`，再自动查找同目录下的本地覆盖文件：

- `bucky_project.local.json`
- `bucky_project.local.yaml`
- `bucky_project.local.yml`

本地覆盖文件只需要写个人要调整的字段，例如：

```yaml
rust_target_dir: /tmp/buckyos-rust-build
rust_env:
  RUSTFLAGS: "-C target-feature=+crt-static"
```

覆盖规则是字典深合并，所以这里的 `rust_env` 会和主配置里的 `rust_env` 合并；同名 key 以本地配置为准。也可以通过 `BUCKYOS_PROJECT_LOCAL_CONFIG=/path/to/local.yaml` 指定本地覆盖文件。

### Web 模块字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定为 "web" |
| `name` | string | ✅ | 模块名称 |
| `src_dir` | string | ✅ | 源代码目录（相对于 base_dir） |
| `target_dir` | array | ❌ | 构建产物输出目录列表 |

### Rust 模块字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定为 "rust" |
| `name` | string | ✅ | 模块名称 |
| `target_dir` | array | ❌ | 编译产物输出目录列表 |

## 💡 使用场景

### 场景 1: 持续集成/部署

```bash
# CI/CD 脚本
#!/bin/bash

# 从配置文件加载项目并构建
python3 << EOF
from buckyos_devkit.project import BuckyProject
from buckyos_devkit.build_web_apps import build_web_modules

project = BuckyProject.from_file('buckyos.json')
build_web_modules(project)
EOF
```

### 场景 2: 多环境配置

```bash
project/
  ├── buckyos.dev.json      # 开发环境配置
  ├── buckyos.staging.json  # 测试环境配置
  └── buckyos.prod.json     # 生产环境配置
```

```python
import os
env = os.getenv('BUILD_ENV', 'dev')
project = BuckyProject.from_file(f'buckyos.{env}.json')
```

### 场景 3: 团队协作

```python
# 团队成员 A 创建配置
project = BuckyProject(name='shared-project')
# ... 添加模块 ...
project.save('buckyos.json')

# 提交到 Git
# git add buckyos.json
# git commit -m "Add project configuration"

# 团队成员 B 拉取并使用
project = BuckyProject.from_file('buckyos.json')
```

## ⚙️ 高级用法

### 配置继承和合并

```python
from buckyos_devkit.project import BuckyProject

# 加载基础配置
base_project = BuckyProject.from_file('buckyos.base.json')

# 加载环境特定配置
env_config = BuckyProject.from_file('buckyos.dev.json')

# 合并配置（手动合并示例）
for module_name, module_info in env_config.modules.items():
    base_project.modules[module_name] = module_info

# 使用合并后的配置
build_web_modules(base_project)
```

### 动态修改配置

```python
project = BuckyProject.from_file('buckyos.json')

# 根据平台调整编译环境变量
import platform
if platform.system() == 'Darwin':
    project.rust_env['MACOSX_DEPLOYMENT_TARGET'] = '11.0'
elif platform.system() == 'Linux':
    project.rust_env['RUSTFLAGS'] = '-C target-feature=+crt-static'

# 修改构建输出目录
project.rust_target_dir = Path('/tmp/my-build')

# 保存修改后的配置
project.save('buckyos.local.json')
```

## 🛠️ 完整构建脚本示例

```python
#!/usr/bin/env python3
"""
完整的构建脚本示例
"""
from pathlib import Path
from buckyos_devkit.project import BuckyProject
from buckyos_devkit.build_web_apps import build_web_modules
from buckyos_devkit.build_rust import build_rust_modules

def main():
    # 从配置文件加载项目
    config_file = Path(__file__).parent / 'buckyos.json'
    
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        print("请创建 buckyos.json 配置文件")
        return 1
    
    print(f"📖 从 {config_file} 加载配置...")
    project = BuckyProject.from_file(config_file)
    
    print(f"🚀 开始构建项目: {project.name}")
    print(f"   基础目录: {project.base_dir}")
    print(f"   模块数量: {len(project.modules)}")
    
    # 构建 Web 模块
    build_web_modules(project)
    
    # 构建 Rust 模块
    # build_rust_modules(project)
    
    print("✅ 构建完成！")
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
```

## 📚 相关文档

- [USAGE_EXAMPLE.md](./USAGE_EXAMPLE.md) - 更多使用示例
- [QUICK_START.md](./QUICK_START.md) - 快速开始指南
- [README.md](./README.md) - 项目概览
