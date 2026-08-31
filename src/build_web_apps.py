import subprocess
from typing import Dict, List

from .module_build import BuildContext, BuildResult, BuildResultSpec
from .project import BuckyProject, ModuleInfo, WebModuleInfo


def _build_pnpm_module(project: BuckyProject, module_name: str) -> BuildResult:
    module_info = project.modules.get(module_name)
    if not isinstance(module_info, WebModuleInfo):
        raise ValueError(f"Web module {module_name} not found")

    work_dir = project.resolve_from_base_dir(module_info.src_dir).resolve()
    package_json = work_dir / "package.json"
    if not package_json.is_file():
        raise FileNotFoundError(f"Web module {module_name} has no package.json: {package_json}")

    label = f"{module_info.type}/{module_info.format}"
    print(f"* Building {label} module {module_name} at {module_info.src_dir} ...")
    for command in ("pnpm install --no-lockfile", "pnpm run build"):
        print(f"**\t{command}")
        subprocess.run(command, shell=True, cwd=work_dir, check=True)

    print(f"Build {label} module {module_name} completed")
    return BuildResult(
        module_key=module_name,
        build_type="web",
        work_dir=work_dir,
    )


def build_web_module(project: BuckyProject, module_name: str) -> BuildResult:
    return _build_pnpm_module(project, module_name)


def build_web_modules(
    project: BuckyProject,
    selected_modules: List[str] | None = None,
) -> Dict[str, BuildResult]:
    web_modules = [
        module_name
        for module_name, module_info in project.modules.items()
        if isinstance(module_info, WebModuleInfo)
    ]
    if selected_modules is not None:
        selected_set = set(selected_modules)
        web_modules = [module_name for module_name in web_modules if module_name in selected_set]
    if not web_modules:
        return {}

    print("🚀 Building web modules ...")
    results = {
        module_name: build_web_module(project, module_name)
        for module_name in web_modules
    }
    print("✅ Build web modules completed")
    return results


class WebBuilder:
    build_type = "web"

    def plan(self, module_key: str, module: ModuleInfo) -> BuildResultSpec:
        if not isinstance(module, WebModuleInfo):
            raise ValueError(f"Web builder received non-Web module {module_key}")
        return BuildResultSpec(build_type=self.build_type)

    def build_modules(
        self,
        project: BuckyProject,
        module_keys: List[str],
        context: BuildContext,
    ) -> Dict[str, BuildResult]:
        return build_web_modules(project, module_keys)
