import os
import subprocess
import json
from typing import List
from .project import BuckyProject, WebAppInfo

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def get_github_dependencies(package_json_path: str) -> List[str]:
    """Extract GitHub dependencies from package.json
    
    Recognizes the following formats:
    - "github:owner/repo"
    - "git+https://github.com/..."
    - "git+ssh://git@github.com/..."
    """
    if not os.path.exists(package_json_path):
        return []
    
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            pkg = json.load(f)
        
        github_deps = []
        dependencies = pkg.get('dependencies', {})
        
        for name, version in dependencies.items():
            if isinstance(version, str):
                # Check if it's a GitHub dependency
                if any(pattern in version.lower() for pattern in ['github:', 'git+https://github.com', 'git+ssh://git@github.com']):
                    github_deps.append(name)
        
        return github_deps
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: unable to read package.json: {e}")
        return []


def build_web_app(project: BuckyProject, app_name: str):
    """Build a web application
    
    Automatically detects and updates GitHub dependencies while keeping other dependencies stable.
    """
    app_info = project.apps[app_name]
    if not app_info:
        raise ValueError(f"Web app {app_name} not found")

    print(f'* Building web app {app_name} at {app_info.src_dir} ...')
    work_dir = os.path.join(project.base_dir, app_info.src_dir)
    package_json = os.path.join(work_dir, 'package.json')
    
    # Detect GitHub dependencies
    github_deps = get_github_dependencies(package_json)
    
    # Build command
    cmd = 'pnpm install'
    
    if github_deps:
        deps_str = ' '.join(github_deps)
        cmd += f' && pnpm update {deps_str}'
        print(f'  -> Will update GitHub dependencies: {", ".join(github_deps)}')
    
    cmd += ' && pnpm run build'
    
    print(f'* Build web app {app_name}:\n**\t{cmd} ')
    subprocess.run(cmd, shell=True, cwd=work_dir, check=True)
    print(f'Build web app {app_name} completed')

def build_web_apps(project: BuckyProject):
    """Build all web applications in the project"""
    print(f'Building web apps ...')
    for app_name, app_info in project.apps.items():
        if isinstance(app_info, WebAppInfo):
            build_web_app(project, app_name)


