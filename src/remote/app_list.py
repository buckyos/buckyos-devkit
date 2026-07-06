from pathlib import Path
import json

class AppConfig:
    """Application configuration"""
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.commands : dict [str, list[str]]= None
        self.directories : dict [str, str] = None
        self.version : str = None

    def load_from_file(self, file_path: Path):
        with open(file_path, 'r') as f:
            app_config = json.load(f)
        app_name = app_config.get("name")
        if app_name is None:
            raise ValueError(f"App name not found in {file_path}")
        if self.app_name != app_name:
            raise ValueError(
                f"App name mismatch in {file_path}: expected '{self.app_name}', got '{app_name}'"
            )

        self.version = app_config.get("version")
        self.commands = app_config.get("commands")
        self.directories = app_config.get("directories")

    def get_command(self, cmd_name: str) -> list[str]:
        return self.commands.get(cmd_name)

    def get_dir(self, dir_name: str) -> str:
        return self.directories.get(dir_name)

class AppList:
    """Application list"""
    def __init__(self, app_dir: Path):
        self.app_dir: Path = app_dir
        self.app_list: dict [str, AppConfig]= {}
        self.external_app_names: set[str] = set()

    def load_app_list(self):
        # Open all json files under app_dir and load them into app_list
        for file in self.app_dir.glob('*.json'):
            app_config = AppConfig(file.stem)
            app_config.load_from_file(file)
            self.app_list[app_config.app_name] = app_config

    def load_external_app_configs(self, app_configs: dict[str, str], base_dir: Path):
        if app_configs is None:
            return
        if not isinstance(app_configs, dict):
            raise ValueError("app_configs must be an object mapping app names to config paths")
        if not app_configs:
            return

        base_dir = Path(base_dir)
        for app_name, config_path in app_configs.items():
            if not isinstance(app_name, str) or not isinstance(config_path, str):
                raise ValueError("app_configs must map app names to config path strings")

            external_path = Path(config_path)
            if not external_path.is_absolute():
                external_path = base_dir / external_path

            if app_name in self.external_app_names:
                raise ValueError(
                    f"Duplicate external app config for app '{app_name}' at '{external_path}'"
                )

            app_config = AppConfig(app_name)
            try:
                app_config.load_from_file(external_path)
            except FileNotFoundError as exc:
                raise ValueError(
                    f"External app config for app '{app_name}' not found at '{external_path}'"
                ) from exc
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in external app config for app '{app_name}' at '{external_path}': {exc}"
                ) from exc
            except Exception as exc:
                raise ValueError(
                    f"Failed to load external app config for app '{app_name}' from '{external_path}': {exc}"
                ) from exc

            if app_name in self.app_list:
                print(
                    f"Warning: external app config for app '{app_name}' at '{external_path}' "
                    "overrides local app config"
                )
            self.app_list[app_name] = app_config
            self.external_app_names.add(app_name)

    def get_app(self, app_name: str) -> AppConfig:
        return self.app_list.get(app_name)
    
    def get_all_app_names(self) -> list[str]:
        return list(self.app_list.keys())
