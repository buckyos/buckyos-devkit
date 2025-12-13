# 测试项目 - 快速功能测试指南

这是一个用于测试 buckyos-devkit 功能的示例项目。

## 📁 目录结构

```
test_project/
├── bucky_project.json          # 项目配置文件
├── web/
│   └── frontend/
│       ├── package.json        # Web 模块的包配置
│       └── dist/               # 构建产物目录
│           └── index.html      # 示例页面
├── rootfs/
│   └── demo_app/               # 应用的 rootfs 目录
│       ├── www/                # Web 模块安装位置
│       ├── bin/daemon/         # Rust 模块安装位置
│       ├── data/               # 数据目录
│       ├── logs/               # 日志目录
│       └── temp/               # 临时目录
├── target/                     # Rust 构建输出目录
│   └── release/                # Release 构建产物
├── test_load_config.py         # 配置加载测试脚本
└── test_build_mock.py          # 模拟构建测试脚本
```

## 🚀 快速测试步骤

### 1. 测试配置文件加载

```bash
cd test_project
python3 test_load_config.py
```

**测试内容：**
- ✅ 加载 JSON 格式的配置文件
- ✅ 解析 modules（Web 模块和 Rust 模块）
- ✅ 解析 apps 及其模块映射关系
- ✅ 保存配置文件

**预期输出：**
- 显示项目信息
- 显示所有模块列表
- 显示所有应用及其包含的模块
- 生成输出配置文件 `bucky_project_test_output.json`

### 2. ⭐ 推荐：使用真实构建和安装功能测试

```bash
cd test_project
python3 test_real_build.py
```

**这是最完整的测试！** 它模拟构建产物，然后调用源代码中的真实函数。

**测试内容：**
- ✅ 准备模拟的 Rust 构建产物（target/release/）
- ✅ 准备模拟的 Web 构建产物（web/frontend/dist/）
- ✅ 调用真实的 `copy_build_results()` 函数
- ✅ 调用真实的 `update_app()` 函数
- ✅ 调用真实的 `install_app_data()` 函数
- ✅ 验证所有结果和目录结构

**预期输出：**
- 创建模拟构建产物
- 复制模块到 rootfs
- 安装应用到测试目录
- 显示完整的验证结果和目录树

### 3. 测试模拟构建流程（旧版，仅供参考）

```bash
cd test_project
python3 test_build_mock.py
```

**测试内容：**
- ⚠️ 这个脚本自己实现了复制逻辑，不使用源代码中的函数
- 仅用于快速验证目录结构

### 3. 测试真实构建命令（需要在实际 BuckyOS 项目中）

如果要测试真实的构建流程，你需要：

```bash
# 在实际的 BuckyOS 项目中
cd /path/to/your/buckyos-project

# 确保有 bucky_project.json 配置文件
# 然后运行构建命令
buckyos-build

# 或者跳过 web 模块构建
buckyos-build --no-build-web-modules

# 指定目标平台
buckyos-build --target=x86_64-unknown-linux-musl
```

## 📝 配置文件说明

### bucky_project.json 结构

```json
{
  "name": "项目名称",
  "base_dir": "项目根目录（相对或绝对路径）",
  
  "modules": {
    "模块名": {
      "type": "web" 或 "rust",
      "name": "模块名称",
      "src_dir": "源代码目录（仅 web 模块需要）"
    }
  },
  
  "apps": {
    "应用名": {
      "name": "应用名称",
      "rootfs": "应用的 rootfs 目录（相对于 base_dir）",
      "default_target_rootfs": "默认安装目标目录",
      "modules": {
        "模块名": "模块在应用中的安装路径"
      },
      "data_paths": ["数据目录列表"],
      "clean_paths": ["需要清理的目录列表"]
    }
  },
  
  "rust_target_dir": "Rust 构建输出目录",
  "rust_env": {
    "环境变量名": "值"
  }
}
```

## 🔍 验证要点

### 1. 配置加载验证

- [ ] modules 正确解析为 WebModuleInfo 或 RustModuleInfo
- [ ] apps 正确解析为 AppInfo
- [ ] 模块到应用的映射关系正确

### 2. 构建流程验证

- [ ] Rust 模块能正确构建到 `rust_target_dir/release/`
- [ ] Web 模块的 dist 目录内容能正确复制
- [ ] 模块能按照 apps 配置复制到正确的位置

### 3. 目录结构验证

运行构建后，检查 `rootfs/demo_app/` 目录：

```
rootfs/demo_app/
├── www/                        # web_frontend 模块
│   └── index.html
├── bin/daemon/                 # test_daemon 模块
│   └── test_daemon
├── data/                       # 数据目录
├── logs/                       # 日志目录
└── temp/                       # 临时目录
```

## 🛠️ 调试技巧

### 查看生成的配置文件

```bash
cat bucky_project_test_output.json | python3 -m json.tool
```

### 检查目录结构

```bash
tree rootfs/
# 或
find rootfs/ -type f -o -type d
```

### 查看文件内容

```bash
cat rootfs/demo_app/www/index.html
cat rootfs/demo_app/bin/daemon/test_daemon
```

## 📚 下一步

1. **在真实项目中测试**：将配置应用到实际的 BuckyOS 项目
2. **测试安装功能**：使用 `buckyos-install` 测试安装流程
3. **测试远程部署**：使用 `buckyos-remote` 测试远程设备管理

## ⚠️ 注意事项

- 测试脚本使用相对路径，确保在 `test_project` 目录下运行
- 模拟构建不依赖真实的 Rust/Node.js 环境
- 真实构建需要安装相应的构建工具链

