from typing import Dict, List

from .module_build import BuildContext, BuildResult, BuildResultSpec
from .project import BuckyProject, ModuleInfo, NoneModuleInfo


def build_none_modules(
    project: BuckyProject,
    module_keys: List[str],
) -> Dict[str, BuildResult]:
    results: Dict[str, BuildResult] = {}
    for module_key in module_keys:
        module = project.modules.get(module_key)
        if not isinstance(module, NoneModuleInfo):
            raise ValueError(f"None builder received non-none module {module_key}")
        results[module_key] = BuildResult(
            module_key=module_key,
            build_type="none",
            work_dir=project.resolve_from_base_dir(module.src_dir).resolve(),
        )
    return results


class NoneBuilder:
    build_type = "none"

    def plan(self, module_key: str, module: ModuleInfo) -> BuildResultSpec:
        if not isinstance(module, NoneModuleInfo):
            raise ValueError(f"None builder received non-none module {module_key}")
        return BuildResultSpec(build_type=self.build_type)

    def build_modules(
        self,
        project: BuckyProject,
        module_keys: List[str],
        context: BuildContext,
    ) -> Dict[str, BuildResult]:
        return build_none_modules(project, module_keys)
