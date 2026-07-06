# TODO: devtest support external app config files

## 背景

当前 `buckyos-devtest` 的 VM workspace 配置由两部分组成：

- `<cwd>/dev_configs/<group>.json`：定义 VM 拓扑、节点参数、每个节点启用哪些 app。
- `<cwd>/dev_configs/apps/*.json`：定义 app 的 build/install/update/start/stop/uninstall 命令和 source/target 目录。

`Workspace.load()` 目前固定扫描 `dev_configs/apps/*.json`，所以当一个 app 的唯一真相源已经在另一个仓库时，使用方只能把 app config 复制一份到当前仓库。例如 BuckyOS 的 `sntest` 需要部署 `web3-gateway`，但 `web3-gateway` 的构建和 SN 配置逻辑实际属于 sibling `cyfs-gateway` 仓库。

这个复制模式会带来两个问题：

- app build/install 命令漂移：SN 仓库更新后，BuckyOS 侧 wrapper 容易落后。
- VM 拓扑与 app 定义耦合：BuckyOS 只想表达“这个 VM 环境需要一个 SN app”，不应该维护 SN app 的内部部署逻辑。

目标是在保持旧 `dev_configs` 完全可用的前提下，让 group 配置显式引用外部 app config 文件。

## 设计目标

- 保持向下兼容：不带新字段的老 `dev_configs` 行为完全不变。
- 保持唯一真相源：外部仓库拥有的 app config 不再需要复制到当前仓库。
- 保持职责清晰：
  - group config 负责 VM 拓扑和 app instance params。
  - app config 负责 app 的命令和目录布局。
- 不引入新依赖。
- 不改变现有命令行接口：`buckyos-devtest <group> install/start/update/...` 继续工作。

## 配置格式

在 `<group>.json` 顶层新增可选字段 `app_configs`：

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
  },
  "instance_order": ["sn"]
}
```

语义：

- `app_configs` 是可选字段；缺省时保持旧行为。
- key 是 app name，必须和目标 app config 文件内的 `"name"` 一致。
- value 是 app config JSON 文件路径。
- 相对路径按 `Workspace.base_dir` 解析，也就是当前 devtest 约定的运行目录 `<repo>/src`。
- 绝对路径按原样使用。
- `nodes.*.apps` 仍然只表示“该节点启用这个 app”以及该 app 在该节点的 instance params，不承载 app config path。

不建议把路径写入 `nodes.*.apps.<app>.config`，因为这会混淆 app instance params 与 app definition。

## 兼容性要求

必须满足：

- 老配置只有 `dev_configs/apps/*.json` 时，行为和当前版本一致。
- 老配置里的 `nodes.*.apps` params 传给命令模板的方式不变，例如 `{{buckyos.node_group}}`、`{{web3-gateway.node_group_name}}`。
- `--apps` 过滤参数行为不变。
- `exec <app>.<cmd>` 行为不变。
- `get_all_app_names()` 仍返回本 workspace 可用 app 列表，包含本地 app configs 和显式外部 app configs。

推荐加载顺序：

1. 先加载本地 `dev_configs/apps/*.json`。
2. 再加载顶层 `app_configs` 指向的文件。
3. 如果外部 app config 与本地 app config 同名，外部显式配置覆盖本地配置，并打印明确日志。
4. 如果两个外部 app config 声明同名 app，直接报错。

这样老配置不受影响，新配置可以在迁移期间同时保留旧 wrapper 文件，但实际使用外部唯一真相源。

## 实现任务

### 1. 扩展 group config 解析

文件：`src/remote/vm_mgr.py`

- 在 `VMNodeList` 中增加 `app_configs: dict[str, str]`。
- `load_from_file()` 读取顶层 `data.get("app_configs", {})`。
- 校验 `app_configs` 必须是 object；否则抛出清晰错误。
- 继续保留现有 `nodes`、`instance_order` 解析逻辑不变。

### 2. 扩展 AppList 加载能力

文件：`src/remote/app_list.py`

- 保留当前扫描 `self.app_dir.glob("*.json")` 的逻辑。
- 新增方法或参数，用于加载显式 app config paths：
  - 输入：`dict[str, str] app_configs`
  - 输入：`Path base_dir`
- 解析规则：
  - absolute path: 直接使用。
  - relative path: `base_dir / path`。
- 加载外部文件时用 `AppConfig(expected_app_name)`，不要用 file stem 推断名称。
- `AppConfig.load_from_file()` 已经校验 JSON 内 `"name"`，继续复用。
- 文件不存在、JSON 格式错误、name mismatch 时给出包含 app name 和 path 的错误信息。
- duplicate 处理：
  - local + explicit duplicate：explicit 覆盖 local，打印 warning。
  - explicit + explicit duplicate：报错。

### 3. 修改 Workspace.load()

文件：`src/remote/worksapce.py`

当前逻辑：

```python
app_dir = self.workspace_dir / "apps"
self.app_list = AppList(app_dir)
self.app_list.load_app_list()
```

调整为：

```python
app_dir = self.workspace_dir / "apps"
self.app_list = AppList(app_dir)
self.app_list.load_app_list()
self.app_list.load_external_app_configs(self.nodes.app_configs, self.base_dir)
```

命名可以不同，但要保持职责：

- `Workspace` 负责把 group config 中的 `app_configs` 交给 `AppList`。
- `AppList` 负责 app config 文件加载和冲突处理。

### 4. 修正 install/update 中的 path bug

文件：`src/remote/worksapce.py`

当前 `install()` 和 `update()` 会计算 resolved path：

```python
source_dir_path = Path(source_dir)
if not source_dir_path.is_absolute():
    source_dir_path = self.base_dir / source_dir_path
```

但随后传给 `remote_device.push()` 的仍然是原始 `source_dir`：

```python
remote_device.push(source_dir, target_dir)
```

应改为传 resolved path：

```python
remote_device.push(str(source_dir_path), target_dir)
```

`update()` 里的 `source_bin_dir_path` 同理。

这不是外部 app config 的核心能力，但外部 app config 更容易使用跨仓库相对路径，不修这个会导致 source/target 解析和实际 push 行为不一致。

### 5. 增加测试

建议新增或扩展测试文件：

- `tests/test_remote_app_list.py`
- `tests/test_remote_workspace_external_app_configs.py`

测试覆盖：

- 旧模式：只有 `dev_configs/apps/demo.json`，加载成功。
- 新模式：`group.json` 顶层 `app_configs` 指向外部文件，加载成功。
- 新模式路径解析：相对路径按 `base_dir` 解析。
- name mismatch：`app_configs.demo` 指向的文件内 `"name": "other"`，应失败。
- missing file：应失败并包含 app name/path。
- local + explicit duplicate：explicit 覆盖 local，并可通过 `get_app()` 看到外部版本。
- `nodes.*.apps` params 不受影响，`get_app_params()` 仍返回原 params。

可用临时目录构造 fixture，不需要真实 Multipass。

### 6. 更新文档

文件建议：

- `USAGE_EXAMPLE.md`
- `QUICK_START.md`
- `TESTING_GUIDE.md`

需要补充：

- `app_configs` 字段示例。
- 路径相对 `Workspace.base_dir`，通常是运行 `buckyos-devtest` 的 `<repo>/src`。
- `nodes.*.apps` 只放 instance params，不放 app config path。
- 外部 app config 适合 sibling repo 场景，例如：

```json
{
  "app_configs": {
    "web3-gateway": "../../cyfs-gateway/src/dev_configs/apps/web3-gateway.json"
  }
}
```

### 7. BuckyOS 侧迁移验证

在 BuckyOS 仓库中验证：

1. `src/dev_configs/sntest.json` 增加：

```json
{
  "app_configs": {
    "web3-gateway": "../../cyfs-gateway/src/dev_configs/apps/web3-gateway.json"
  }
}
```

2. 保留旧 `src/dev_configs/apps/web3-gateway.json` 时，确认 explicit external config 覆盖本地 config。
3. 删除旧 `src/dev_configs/apps/web3-gateway.json` 后，确认：

```bash
cd /Users/liuzhicong/project/buckyos/src
uv run buckyos-devtest sntest install
uv run buckyos-devtest sntest start
```

仍能找到并部署 `web3-gateway`。

## 非目标

- 不负责 clone 或 checkout 外部仓库；相邻仓库路径仍由开发环境约定保证。
- 不引入 package registry 或 app config registry。
- 不改变 app config JSON 的 schema。
- 不改变现有命令模板变量语法。
- 不移除 `dev_configs/apps/*.json` 支持。

## 验收标准

- devkit 单测通过。
- 旧 dev_configs fixtures 不需要修改即可通过。
- 使用顶层 `app_configs` 的新配置可以加载外部 app config。
- BuckyOS `sntest` 可以不复制 `web3-gateway.json`，直接引用 sibling `cyfs-gateway` 中的 app config。
- 错误场景有清晰提示，至少包含 app name 和 config path。

## 风险与注意事项

- 相对路径基准必须明确使用 `Workspace.base_dir`，不要使用 `workspace_dir`，否则从 `buckyos/src` 引用 `../../cyfs-gateway/...` 会解析错。
- 本地 duplicate 覆盖需要打印日志，避免开发者不知道实际使用的是外部配置。
- app config 里的 `directories.source`、`directories.source_bin` 仍然按现有规则相对 `base_dir` 解析；如果外部 app config 希望使用自己仓库内的相对路径，后续可以再设计 `config_dir` 基准，但本次先不扩大范围。
- Windows 路径需要覆盖基本测试，至少保证 absolute path 不被误拼接。

