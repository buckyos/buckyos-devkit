from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Any
import platform
import tempfile
import json
import os

if platform.system() == "Windows":
    _temp_dir = tempfile.gettempdir()
else:
    _temp_dir = "/tmp/"

@dataclass
class WebModuleInfo:
    name: str
    src_dir: Path 
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebModuleInfo':
        """Create WebModuleInfo from dictionary"""
        return cls(
            name=data['name'],
            src_dir=Path(data['src_dir'])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'src_dir': str(self.src_dir)
        }

@dataclass
class RustModuleInfo:
    name: str
    file_only: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RustModuleInfo':
        """Create RustModuleInfo from dictionary"""
        return cls(
            name=data['name'],
            file_only=data.get('file_only', False)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'file_only': self.file_only
        }

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
    base_dir: Path = field(default_factory=Path.cwd)
    modules: Dict[str, WebModuleInfo | RustModuleInfo] = field(default_factory=dict)
    apps: Dict[str, AppInfo] = field(default_factory=dict)

    rust_target_dir: Optional[Path] = None
    rust_env: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize fields that depend on other fields"""
        if self.rust_target_dir is None:
            self.rust_target_dir = Path(_temp_dir) / "rust_build" / self.name

    def add_web_module(self, module: str, info: WebModuleInfo) -> None:
        """Add a web module"""
        if module in self.modules:
            raise ValueError(f"Web module {module} already exists")
        self.modules[module] = info
    
    def add_rust_module(self, module: str, info: RustModuleInfo) -> None:
        """Add a Rust module"""
        if module in self.modules:
            raise ValueError(f"Rust module {module} already exists")
        self.modules[module] = info
    
    @classmethod
    def from_file(cls, config_file: str | Path) -> 'BuckyProject':
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
        config_file = Path(config_file)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        # Select parser based on file extension
        suffix = config_file.suffix.lower()
        
        if suffix == '.json':
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        elif suffix in ['.yaml', '.yml']:
            try:
                import yaml
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            except ImportError:
                raise ImportError(
                    "PyYAML is required to load YAML files: pip install pyyaml"
                )
        else:
            raise ValueError(f"Unsupported config file format: {suffix}, only .json, .yaml, .yml are supported")
        
        return cls.from_dict(data, config_file.parent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[Path] = None) -> 'BuckyProject':
        """Create project configuration from dictionary
        
        Args:
            data: Configuration data dictionary
            base_dir: Base directory, used if not specified in data
        """
        # Handle base directory
        if 'base_dir' in data:
            base_dir = Path(data['base_dir'])
        elif base_dir is None:
            base_dir = Path.cwd()
        
        # Parse modules
        modules: Dict[str, WebModuleInfo | RustModuleInfo] = {}
        for module_name, module_data in data.get('modules', {}).items():
            module_type = module_data.get('type', 'web')
            if module_type == 'web':
                modules[module_name] = WebModuleInfo.from_dict(module_data)
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
            base_dir=base_dir,
            modules=modules,
            apps=apps,
            rust_env=data.get('rust_env', {})
        )
        
        # Handle rust_target_dir
        if 'rust_target_dir' in data:
            project.rust_target_dir = Path(data['rust_target_dir'])
        
        return project
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        modules_dict = {}
        for module_name, module_info in self.modules.items():
            module_dict = module_info.to_dict()
            if isinstance(module_info, WebModuleInfo):
                module_dict['type'] = 'web'
            elif isinstance(module_info, RustModuleInfo):
                module_dict['type'] = 'rust'
            modules_dict[module_name] = module_dict
        
        apps_dict = {}
        for app_name, app_info in self.apps.items():
            apps_dict[app_name] = app_info.to_dict()
        
        return {
            'name': self.name,
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
        for name in ['bucky_project.json', 'bucky_project.yaml', 'bucky_project.yml']:
            path = Path.cwd() / name
            if path.exists():
                return path
        return None
