from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
from typing import List, Dict, Optional, Any
import platform
import tempfile
import json
import os

if platform.system() == "Windows":
    _temp_dir = tempfile.gettempdir()
else:
    _temp_dir = "/tmp/"

@dataclass(frozen=True)
class PikgModuleConfig:
    meta_dir: Path = Path("dapp_meta")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PikgModuleConfig':
        if not isinstance(data, dict):
            raise ValueError("pikg must be an object")
        unknown = set(data) - {"meta_dir"}
        if unknown:
            raise ValueError(f"Unknown pikg option(s): {', '.join(sorted(unknown))}")
        meta_dir = data.get("meta_dir", "dapp_meta")
        if not isinstance(meta_dir, str) or not meta_dir:
            raise ValueError("pikg.meta_dir must be a non-empty string")
        return cls(meta_dir=Path(meta_dir))

    def to_dict(self) -> Dict[str, Any]:
        if self.meta_dir == Path("dapp_meta"):
            return {}
        return {"meta_dir": str(self.meta_dir)}


def _parse_format_options(data: Dict[str, Any]) -> tuple[str, Optional[PikgModuleConfig]]:
    artifact_format = data.get("format", "files")
    if not isinstance(artifact_format, str) or not artifact_format:
        raise ValueError("Module format must be a non-empty string")
    pikg_data = data.get("pikg")
    if artifact_format != "pikg" and pikg_data is not None:
        raise ValueError("Only format: pikg modules may contain a pikg config block")
    pikg = (
        PikgModuleConfig.from_dict({} if pikg_data is None else pikg_data)
        if artifact_format == "pikg"
        else None
    )
    return artifact_format, pikg


def _add_format_options(result: Dict[str, Any], artifact_format: str, pikg: Optional[PikgModuleConfig]) -> None:
    if artifact_format != "files":
        result["format"] = artifact_format
    if artifact_format == "pikg" and pikg is not None:
        pikg_data = pikg.to_dict()
        if pikg_data:
            result["pikg"] = pikg_data


@dataclass
class NoneModuleInfo:
    name: str
    src_dir: Path
    type: str = "none"
    format: str = "files"
    pikg: Optional[PikgModuleConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NoneModuleInfo':
        artifact_format, pikg = _parse_format_options(data)
        src_dir = data.get('src_dir')
        if not isinstance(src_dir, str) or not src_dir:
            raise ValueError("None module src_dir must be a non-empty string")
        return cls(
            name=data['name'],
            src_dir=Path(src_dir),
            format=artifact_format,
            pikg=pikg,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'name': self.name,
            'src_dir': str(self.src_dir),
        }
        _add_format_options(result, self.format, self.pikg)
        return result


@dataclass
class WebModuleInfo:
    name: str
    src_dir: Path
    type: str = "web"
    format: str = "files"
    pikg: Optional[PikgModuleConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebModuleInfo':
        artifact_format, pikg = _parse_format_options(data)
        return cls(
            name=data['name'],
            src_dir=Path(data['src_dir']),
            format=artifact_format,
            pikg=pikg,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'name': self.name,
            'src_dir': str(self.src_dir),
        }
        _add_format_options(result, self.format, self.pikg)
        return result


@dataclass
class RustModuleInfo:
    name: str
    file_only: bool = False
    type: str = "rust"
    format: str = "files"
    pikg: Optional[PikgModuleConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RustModuleInfo':
        artifact_format, pikg = _parse_format_options(data)
        return cls(
            name=data['name'],
            file_only=data.get('file_only', False),
            format=artifact_format,
            pikg=pikg,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'name': self.name,
            'file_only': self.file_only,
        }
        _add_format_options(result, self.format, self.pikg)
        return result


ModuleInfo = NoneModuleInfo | WebModuleInfo | RustModuleInfo

@dataclass
class AppInfo:
    name: str
    rootfs: Path # 相对Project的base_dir的相对路径
    default_target_rootfs: Path
    
    # 模块名 => 模块的安装路径
    modules: Dict[str, str] = field(default_factory=dict)
    data_paths: List[Path] = field(default_factory=list)
    clean_paths: List[Path] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppInfo':
        """Create AppInfo from dictionary"""
        modules = {}
        for mod_name, mod_path in data.get('modules', {}).items():
            modules[mod_name] = mod_path
        
        return cls(
            name=data['name'],
            rootfs=Path(data['rootfs']),
            default_target_rootfs=Path(data['default_target_rootfs']),
            modules=modules,
            data_paths=[Path(p) for p in data.get('data_paths', [])],
            clean_paths=[Path(p) for p in data.get('clean_paths', [])]
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'rootfs': str(self.rootfs),
            'default_target_rootfs': str(self.default_target_rootfs),
            'modules': {k: str(v) for k, v in self.modules.items()},
            'data_paths': [str(p) for p in self.data_paths],
            'clean_paths': [str(p) for p in self.clean_paths]
        }

@dataclass
class BuckyProject:
    """BuckyOS project configuration"""
    name: str
    version: str
    base_dir: Path = field(default_factory=Path.cwd)
    config_dir: Optional[Path] = None
    modules: Dict[str, ModuleInfo] = field(default_factory=dict)
    apps: Dict[str, AppInfo] = field(default_factory=dict)

    rust_target_dir: Optional[Path] = None
    rust_env: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize fields that depend on other fields"""
        self.base_dir = Path(self.base_dir)
        if self.config_dir is None:
            self.config_dir = self.base_dir
        else:
            self.config_dir = Path(self.config_dir)
        if self.rust_target_dir is None:
            self.rust_target_dir = Path(_temp_dir) / "rust_build" / self.name

    def add_web_module(self, module: str, info: WebModuleInfo) -> None:
        """Add a web module"""
        if module in self.modules:
            raise ValueError(f"Web module {module} already exists")
        self.modules[module] = info

    def add_none_module(self, module: str, info: NoneModuleInfo) -> None:
        """Add a module with no build step."""
        if module in self.modules:
            raise ValueError(f"None module {module} already exists")
        self.modules[module] = info


    def add_rust_module(self, module: str, info: RustModuleInfo) -> None:
        """Add a Rust module"""
        if module in self.modules:
            raise ValueError(f"Rust module {module} already exists")
        self.modules[module] = info

    @staticmethod
    def _expand_path(path: str | Path) -> Path:
        return Path(os.path.expanduser(os.path.expandvars(os.fspath(path))))

    @staticmethod
    def _load_config_data(config_file: str | Path) -> Dict[str, Any]:
        config_file = Path(config_file).expanduser().resolve()

        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        suffix = config_file.suffix.lower()

        if suffix == '.json':
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif suffix in ['.yaml', '.yml']:
            try:
                import yaml
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                return {} if data is None else data
            except ImportError:
                raise ImportError(
                    "PyYAML is required to load YAML files: pip install pyyaml"
                )
        else:
            raise ValueError(f"Unsupported config file format: {suffix}, only .json, .yaml, .yml are supported")

    @staticmethod
    def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = BuckyProject._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def resolve_from_config(self, path: str | Path) -> Path:
        path_obj = self._expand_path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.config_dir / path_obj

    def resolve_from_base_dir(self, path: str | Path) -> Path:
        path_obj = self._expand_path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.base_dir / path_obj

    @staticmethod
    def _validate_pikg_install_path(module_name: str, app_name: str, module_path: str) -> None:
        if not isinstance(module_path, str):
            raise ValueError(f"PIKG module {module_name} install path for app {app_name} must be a string")
        normalized = module_path.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or normalized.endswith("/")
            or path.is_absolute()
            or (len(normalized) >= 2 and normalized[1] == ":")
            or any(part in ("", ".", "..") for part in path.parts)
        ):
            raise ValueError(
                f"PIKG module {module_name} has unsafe install path for app {app_name}: {module_path}"
            )
        if path.suffix.lower() != ".pikg":
            raise ValueError(
                f"PIKG module {module_name} install path for app {app_name} must end with .pikg: {module_path}"
            )

    def validate(self) -> None:
        for module_name, module_info in self.modules.items():
            if module_info.type not in {"none", "web", "rust"}:
                raise ValueError(f"Unknown module type: {module_info.type}")
            if module_info.format not in {"files", "pikg"}:
                raise ValueError(f"Unknown module format: {module_info.format}")
            if module_info.format != "pikg" and module_info.pikg is not None:
                raise ValueError(
                    f"Only format: pikg module {module_name} may contain a pikg config block"
                )
            if module_info.format != "pikg":
                continue

            install_refs = []
            for app_name, app_info in self.apps.items():
                if module_name not in app_info.modules:
                    continue
                module_path = app_info.modules[module_name]
                self._validate_pikg_install_path(module_name, app_name, module_path)
                rootfs = self.resolve_from_base_dir(app_info.rootfs).resolve()
                staging_path = (rootfs / module_path).resolve()
                try:
                    staging_path.relative_to(rootfs)
                except ValueError as error:
                    raise ValueError(
                        f"PIKG module {module_name} install path escapes app {app_name} rootfs: {module_path}"
                    ) from error
                install_refs.append((app_name, staging_path))
            if not install_refs:
                raise ValueError(
                    f"PIKG module {module_name} must have at least one same-key app module install entry"
                )
    
    @classmethod
    def from_file(cls, config_file: str | Path, overlay_files: Optional[List[str | Path]] = None) -> 'BuckyProject':
        """Load project configuration from file
        
        Supports JSON and YAML formats.
        
        Args:
            config_file: Path to config file (.json, .yaml, .yml)
        
        Returns:
            BuckyProject instance
        
        Example:
            # Load from JSON
            project = BuckyProject.from_file('buckyos.json')
            
            # Load from YAML
            project = BuckyProject.from_file('buckyos.yaml')
        
        Config file example (JSON):
        {
            "name": "my-project",
            "base_dir": "/path/to/project",
            "modules": {
                "frontend": {
                    "type": "web",
                    "name": "frontend",
                    "src_dir": "web/frontend",
                    "target_dir": ["rootfs/modules/frontend"]
                },
                "backend": {
                    "type": "rust",
                    "name": "backend",
                    "target_dir": ["rootfs/bin"]
                }
            },
            "rust_env": {
                "RUSTFLAGS": "-C target-feature=+crt-static"
            }
        }
        """
        config_file = Path(config_file).expanduser().resolve()
        data = cls._load_config_data(config_file)
        for overlay_file in overlay_files or []:
            overlay_data = cls._load_config_data(overlay_file)
            data = cls._deep_merge_dicts(data, overlay_data)
        
        return cls.from_dict(data, config_file.parent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[Path] = None) -> 'BuckyProject':
        """Create project configuration from dictionary
        
        Args:
            data: Configuration data dictionary
            base_dir: Config file directory, used if not specified in data
        """
        config_dir = Path.cwd() if base_dir is None else cls._expand_path(base_dir)
        if not config_dir.is_absolute():
            config_dir = Path.cwd() / config_dir
        config_dir = config_dir.resolve()

        # Handle base directory
        if 'base_dir' in data:
            project_base_dir = cls._expand_path(data['base_dir'])
            if not project_base_dir.is_absolute():
                project_base_dir = config_dir / project_base_dir
        else:
            project_base_dir = config_dir

        # Parse modules
        modules: Dict[str, ModuleInfo] = {}
        for module_name, module_data in data.get('modules', {}).items():
            module_type = module_data.get('type', 'none')
            if module_type == 'none':
                modules[module_name] = NoneModuleInfo.from_dict(module_data)
            elif module_type == 'web':
                modules[module_name] = WebModuleInfo.from_dict(module_data)
            elif module_type == 'web-pikg':
                raise ValueError(
                    "Unsupported module type: web-pikg; use type: web with format: pikg"
                )
            elif module_type == 'rust':
                modules[module_name] = RustModuleInfo.from_dict(module_data)
            else:
                raise ValueError(f"Unknown module type: {module_type}")
        
        # Parse apps
        apps: Dict[str, AppInfo] = {}
        for app_name, app_data in data.get('apps', {}).items():
            apps[app_name] = AppInfo.from_dict(app_data)
        
        # Create project
        project = cls(
            name=data['name'],
            version=data.get('version', '0.1.0'),
            base_dir=project_base_dir,
            config_dir=config_dir,
            modules=modules,
            apps=apps,
            rust_env=data.get('rust_env', {})
        )
        
        # Handle rust_target_dir
        if 'rust_target_dir' in data:
            project.rust_target_dir = project.resolve_from_config(data['rust_target_dir'])

        project.validate()
        return project
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        modules_dict = {}
        for module_name, module_info in self.modules.items():
            module_dict = module_info.to_dict()
            if isinstance(module_info, NoneModuleInfo):
                pass
            elif isinstance(module_info, WebModuleInfo):
                module_dict['type'] = 'web'
            elif isinstance(module_info, RustModuleInfo):
                module_dict['type'] = 'rust'
            modules_dict[module_name] = module_dict
        
        apps_dict = {}
        for app_name, app_info in self.apps.items():
            apps_dict[app_name] = app_info.to_dict()
        
        return {
            'name': self.name,
            'version': self.version,
            'base_dir': str(self.base_dir),
            'modules': modules_dict,
            'apps': apps_dict,
            'rust_target_dir': str(self.rust_target_dir),
            'rust_env': self.rust_env
        }
    
    def save(self, config_file: str | Path) -> None:
        """Save configuration to file
        
        Args:
            config_file: Path to config file
        
        Example:
            project.save('buckyos.json')
            project.save('buckyos.yaml')
        """
        config_file = Path(config_file)
        suffix = config_file.suffix.lower()
        
        data = self.to_dict()
        
        if suffix == '.json':
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        elif suffix in ['.yaml', '.yml']:
            try:
                import yaml
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
            except ImportError:
                raise ImportError(
                    "PyYAML is required to save YAML files: pip install pyyaml"
                )
        else:
            raise ValueError(f"Unsupported config file format: {suffix}, only .json, .yaml, .yml are supported")
        
        print(f"Config saved to: {config_file}")
    @classmethod
    def get_project_config_file(cls) -> Optional[Path]:
        """Get the project configuration file"""
        cwd = Path.cwd()
        search_dirs = [cwd, cwd / 'src']

        for search_dir in search_dirs:
            for name in ['bucky_project.json', 'bucky_project.yaml', 'bucky_project.yml']:
                path = search_dir / name
                if path.exists():
                    return path
        return None

    @classmethod
    def get_project_local_config_file(cls, config_file: str | Path) -> Optional[Path]:
        """Get the optional user-local project configuration file."""
        env_path = os.environ.get("BUCKYOS_PROJECT_LOCAL_CONFIG")
        if env_path:
            path = cls._expand_path(env_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            path = path.resolve()
            if not path.exists():
                raise FileNotFoundError(f"Local config file not found: {path}")
            return path

        config_dir = Path(config_file).expanduser().resolve().parent
        for name in ['bucky_project.local.json', 'bucky_project.local.yaml', 'bucky_project.local.yml']:
            path = config_dir / name
            if path.exists():
                return path
        return None
