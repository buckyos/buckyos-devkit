# 功能测试指南

本指南帮助你快速验证 buckyos-devkit 的核心功能。

## 🎯 测试环境

我们已经为你准备了一个完整的测试项目在 `test_project/` 目录下。

## 📋 测试清单

### ✅ 第一步：测试配置文件加载

```bash
cd test_project
python3 test_load_config.py
```

**验证点：**
- [x] JSON 配置文件能否正确加载
- [x] modules 字段解析正确（WebModuleInfo 和 RustModuleInfo）
- [x] apps 字段解析正确（AppInfo）
- [x] 模块到应用的映射关系正确
- [x] 配置文件能否正确保存

**预期结果：**
```
✅ 配置加载成功!
✅ 配置已保存到: bucky_project_test_output.json
```

---

### ✅ 第二步：⭐ 真实构建和安装功能测试（推荐）

```bash
cd test_project
python3 test_real_build.py
```

**这是最完整的测试！** 使用源代码中的真实函数进行测试。

**验证点：**
- [x] 准备模拟的 Rust 和 Web 构建产物
- [x] 调用真实的 `copy_build_results()` 函数
- [x] 调用真实的 `update_app()` 函数  
- [x] 调用真实的 `install_app_data()` 函数
- [x] 验证 rootfs 目录结构
- [x] 验证测试安装目录结构

**预期结果：**
```
✅ 所有测试通过！

📂 Rootfs 目录:
demo_app/
  ├── bin/daemon/test_daemon    ← Rust 模块
  ├── www/                      ← Web 模块
  ├── data/
  ├── logs/
  └── temp/

📂 测试安装目录:
test_install/demo_app/
  ├── bin/daemon/test_daemon
  ├── www/
  ├── data/
  └── logs/
```

**测试覆盖的源代码函数：**
- ✅ `src/prepare_rootfs.py::copy_build_results()`
- ✅ `src/prepare_rootfs.py::copy_rust_module()`
- ✅ `src/prepare_rootfs.py::copy_web_module()`
- ✅ `src/install.py::update_app()`
- ✅ `src/install.py::install_app_data()`
- ✅ `src/install.py::clean_app()`

---

### 📝 第三步：查看测试结果

#### 1. 验证配置序列化/反序列化

```bash
cd test_project
cat bucky_project_test_output.json | python3 -m json.tool
```

应该看到完整的配置结构，包括 modules 和 apps。

#### 2. 验证构建产物

```bash
cd test_project

# 查看目录树
tree rootfs/ 2>/dev/null || find rootfs/ -print

# 验证 Web 模块
cat rootfs/demo_app/www/index.html

# 验证 Rust 模块
cat rootfs/demo_app/bin/daemon/test_daemon
```

#### 3. 验证模拟的 Rust 构建产物

```bash
cd test_project
ls -lh target/release/
cat target/release/test_daemon
```

---

### ✅ 第四步：测试 devtest 外部 app config

```bash
pytest tests/test_remote_app_list.py tests/test_remote_workspace_external_app_configs.py
```

**验证点：**
- [x] 老模式 `dev_configs/apps/*.json` 不需要修改即可加载
- [x] group 配置顶层 `app_configs` 可以引用外部 app config
- [x] `app_configs` 相对路径按 `Workspace.base_dir` 解析，通常是运行 `buckyos-devtest` 的 `<repo>/src`
- [x] 本地 app config 与外部显式配置同名时，外部配置覆盖本地配置并打印 warning
- [x] `nodes.*.apps` 只保存 instance params，不保存 app config path

示例：

```json
{
  "app_configs": {
    "web3-gateway": "../../cyfs-gateway/src/dev_configs/apps/web3-gateway.json"
  },
  "nodes": {
    "sn": {
      "apps": {
        "web3-gateway": {
          "node_group_name": "sn_server"
        }
      }
    }
  }
}
```

---

## 🔧 真实环境测试（需要实际的 BuckyOS 项目）

如果你有一个真实的 BuckyOS 项目，可以这样测试：

### 1. 准备配置文件

在你的项目根目录创建 `bucky_project.json`：

```json
{
  "name": "your-project",
  "base_dir": ".",
  "modules": {
    "your_web_module": {
      "type": "web",
      "name": "your_web_module",
      "src_dir": "path/to/web/module"
    },
    "your_rust_module": {
      "type": "rust",
      "name": "your_rust_module"
    }
  },
  "apps": {
    "your_app": {
      "name": "your_app",
      "rootfs": "rootfs/your_app",
      "default_target_rootfs": "/opt/buckyos/your_app",
      "modules": {
        "your_web_module": "www",
        "your_rust_module": "bin"
      }
    }
  }
}
```

### 2. 运行真实构建

```bash
# 完整构建
buckyos-build

# 跳过 Web 模块构建
buckyos-build --no-build-web-modules

# 指定目标平台
buckyos-build --target=x86_64-unknown-linux-musl
```

### 3. 测试安装

```bash
# 本地安装
sudo buckyos-install

# 查看安装结果
ls -la /opt/buckyos/
```

---

## 🐛 常见问题排查

### 问题 1: 配置加载失败

```bash
# 检查配置文件语法
cd test_project
python3 -m json.tool bucky_project.json
```

### 问题 2: 模块复制失败

```bash
# 检查源文件是否存在
ls -la web/frontend/dist/
ls -la target/release/

# 检查目标目录权限
ls -ld rootfs/demo_app/
```

### 问题 3: 路径问题

确保所有路径都是相对于 `base_dir` 的相对路径，或者使用绝对路径。

---

## 📊 测试报告模板

完成测试后，可以填写以下报告：

```
测试日期: ____________________
测试环境: ____________________

[ ] 配置加载测试 - 通过/失败
    备注: _________________

[ ] 模拟构建测试 - 通过/失败
    备注: _________________

[ ] 真实构建测试 - 通过/失败
    备注: _________________

[ ] 安装测试 - 通过/失败
    备注: _________________

遇到的问题:
1. _____________________
2. _____________________

改进建议:
1. _____________________
2. _____________________
```

---

## 🎓 下一步学习

1. **深入了解配置**：查看 `PROJECT_CONFIG_EXAMPLE.md`
2. **使用示例**：查看 `USAGE_EXAMPLE.md`
3. **快速开始**：查看 `QUICK_START.md`

---

## 💡 提示

- 测试脚本位于 `test_project/` 目录
- 可以修改 `test_project/bucky_project.json` 来测试不同的配置
- 模拟测试不需要安装 Rust 或 Node.js 环境
- 真实测试需要完整的开发环境
