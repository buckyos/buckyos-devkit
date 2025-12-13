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
class WebAppInfo:
    name: str
    src_dir: Path 
    target_dir: List[Path]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebAppInfo':
        """Create WebAppInfo from dictionary"""
        return cls(
            name=data['name'],
            src_dir=Path(data['src_dir']),
            target_dir=[Path(p) for p in data.get('target_dir', [])]
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'src_dir': str(self.src_dir),
            'target_dir': [str(p) for p in self.target_dir]
        }

@dataclass
class RustAppInfo:
    name: str
    target_dir: List[Path]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RustAppInfo':
        """Create RustAppInfo from dictionary"""
        return cls(
            name=data['name'],
            target_dir=[Path(p) for p in data.get('target_dir', [])]
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'target_dir': [str(p) for p in self.target_dir]
        }

@dataclass
class BuckyProject:
    """BuckyOS project configuration"""
    name: str
    base_dir: Path = field(default_factory=Path.cwd)
    apps: Dict[str, WebAppInfo | RustAppInfo] = field(default_factory=dict)
    
    rust_target_dir: Path = field(default_factory=lambda: Path(_temp_dir) / "rust_build")
    rust_env: Dict[str, str] = field(default_factory=dict)

    def add_web_app(self, app: str, info: WebAppInfo) -> None:
        """Add a web application"""
        if app in self.apps:
            raise ValueError(f"Web app {app} already exists")
        self.apps[app] = info
    
    def add_rust_app(self, app: str, info: RustAppInfo) -> None:
        """Add a Rust application"""
        if app in self.apps:
            raise ValueError(f"Rust app {app} already exists")
        self.apps[app] = info
    
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
            "apps": {
                "frontend": {
                    "type": "web",
                    "name": "frontend",
                    "src_dir": "web/frontend",
                    "target_dir": ["rootfs/apps/frontend"]
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
        
        # Parse apps
        apps: Dict[str, WebAppInfo | RustAppInfo] = {}
        for app_name, app_data in data.get('apps', {}).items():
            app_type = app_data.get('type', 'web')
            if app_type == 'web':
                apps[app_name] = WebAppInfo.from_dict(app_data)
            elif app_type == 'rust':
                apps[app_name] = RustAppInfo.from_dict(app_data)
            else:
                raise ValueError(f"Unknown application type: {app_type}")
        
        # Create project
        project = cls(
            name=data['name'],
            base_dir=base_dir,
            apps=apps,
            rust_env=data.get('rust_env', {})
        )
        
        # Handle rust_target_dir
        if 'rust_target_dir' in data:
            project.rust_target_dir = Path(data['rust_target_dir'])
        
        return project
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        apps_dict = {}
        for app_name, app_info in self.apps.items():
            app_dict = app_info.to_dict()
            if isinstance(app_info, WebAppInfo):
                app_dict['type'] = 'web'
            elif isinstance(app_info, RustAppInfo):
                app_dict['type'] = 'rust'
            apps_dict[app_name] = app_dict
        
        return {
            'name': self.name,
            'base_dir': str(self.base_dir),
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
