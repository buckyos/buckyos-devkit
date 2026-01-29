import sys
import platform
from typing import Optional

from .build_web_apps import build_web_modules
from .build_rust import build_rust_modules
from .project import BuckyProject, WebModuleInfo, RustModuleInfo
from .prepare_rootfs import copy_build_results

def _prompt_select_modules_line(selectable: list[tuple[str, str]]) -> set[str]:
    print("Select modules to build (answer y to include):")
    selected = set()
    for module_name, module_type in selectable:
        answer = input(f"[ ] {module_name} ({module_type}) build? [y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            selected.add(module_name)

    print("Selection:")
    for module_name, module_type in selectable:
        mark = "*" if module_name in selected else " "
        print(f"[{mark}] {module_name} ({module_type})")

    return selected

def _prompt_select_modules_interactive(selectable: list[tuple[str, str]]) -> set[str] | None:
    try:
        import curses
    except Exception:
        return None

    cancel_token = object()

    def _run(stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        selected_flags = [False] * len(selectable)
        index = 0
        while True:
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()
            if max_y < 4 or max_x < 20:
                return None
            header = "Select modules to build: up/down move, space toggle, Enter confirm"
            try:
                stdscr.addstr(0, 0, header[: max_x - 1])
            except curses.error:
                return None

            visible_rows = max_y - 2
            start = 0
            if index >= start + visible_rows:
                start = index - visible_rows + 1
            if index < start:
                start = index

            for row in range(visible_rows):
                i = start + row
                if i >= len(selectable):
                    break
                module_name, module_type = selectable[i]
                prefix = "[*]" if selected_flags[i] else "[ ]"
                line = f"{prefix} {module_name} ({module_type})"
                line = line[: max_x - 1]
                if i == index:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(row + 2, 0, line)
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(row + 2, 0, line)
            stdscr.refresh()

            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                index = (index - 1) % len(selectable)
            elif key in (curses.KEY_DOWN, ord("j")):
                index = (index + 1) % len(selectable)
            elif key == ord(" "):
                selected_flags[index] = not selected_flags[index]
            elif key in (curses.KEY_ENTER, 10, 13):
                return selected_flags
            elif key in (27, ord("q")):
                return cancel_token

    try:
        flags = curses.wrapper(_run)
    except Exception:
        return None

    if flags is None:
        return None
    if flags is cancel_token:
        return set()
    if not flags:
        return set()

    selected = {
        module_name
        for (module_name, _), flag in zip(selectable, flags)
        if flag
    }
    return selected

def _prompt_select_modules(project: BuckyProject, skip_web_module: bool) -> set[str]:
    selectable = []
    for module_name, module_info in project.modules.items():
        if skip_web_module and isinstance(module_info, WebModuleInfo):
            continue
        if isinstance(module_info, WebModuleInfo):
            module_type = "web"
        elif isinstance(module_info, RustModuleInfo):
            module_type = "rust"
        else:
            continue
        selectable.append((module_name, module_type))

    if not selectable:
        print("No buildable modules found.")
        return set()

    if sys.stdin.isatty() and sys.stdout.isatty():
        selected = _prompt_select_modules_interactive(selectable)
        if selected is not None:
            return selected

    return _prompt_select_modules_line(selectable)

def build(project: BuckyProject, rust_target: str, skip_web_module: bool, selected_modules: set[str] | None = None):
    if not skip_web_module:
        build_web_modules(project, None if selected_modules is None else list(selected_modules))
    build_rust_modules(project, rust_target, None if selected_modules is None else list(selected_modules))
    copy_build_results(project, skip_web_module, rust_target, None if selected_modules is None else list(selected_modules))

def build_main():
    from pathlib import Path
    
    skip_web_module = False
    system = platform.system() # Linux / Windows / Darwin
    arch = platform.machine() # x86_64 / AMD64 / arm64 / arm
    print(f"DEBUG: system:{system},arch:{arch}")
    target = ""
    select_mode = False
    selected_modules = None
    if system == "Linux" and (arch == "x86_64" or arch == "AMD64"):
        target = "x86_64-unknown-linux-musl"
    elif system == "Windows" and (arch == "x86_64" or arch == "AMD64"):
        target = "x86_64-pc-windows-msvc"
#     elif system == "Linux" and (arch == "x86_64" or arch == "AMD64"):
#         target = "aarch64-unknown-linux-gnu"
    elif system == "Darwin" and (arch == "arm64" or arch == "arm"):
        target = "aarch64-apple-darwin"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--skip-web":
            skip_web_module = True
            i += 1
            continue
        if arg == "--select" or arg == "-s":
            # Examples: "-s mod_a mod_b" builds those modules; "-s" enters interactive selection.
            modules = []
            j = i + 1
            while j < len(args) and not args[j].startswith("-"):
                modules.append(args[j])
                j += 1
            if modules:
                if selected_modules is None:
                    selected_modules = set(modules)
                else:
                    selected_modules.update(modules)
            elif selected_modules is None:
                select_mode = True
            i = j
            continue
        if arg == "amd64":
            target = "x86_64-unknown-linux-musl"
            i += 1
            continue
        if arg == "aarch64":
            target = "aarch64-unknown-linux-musl"
            i += 1
            continue
        if arg.startswith("--target="):
            target = arg.split("=", 1)[1]
            i += 1
            continue
        i += 1

    # Load project configuration
    # Load project configuration
    config_file : Optional[Path] = BuckyProject.get_project_config_file()
    if config_file is None:
        print("Error: No bucky_project.json or bucky_project.yaml configuration file found in current directory")
        sys.exit(1)
    
    print(f"Loading project configuration from: {config_file}")
    bucky_project = BuckyProject.from_file(config_file)

    if selected_modules is None and select_mode:
        selected_modules = _prompt_select_modules(bucky_project, skip_web_module)
        if not selected_modules:
            print("No modules selected; build skipped.")
            return

    print(f"Rust target is : {target}")
    build(bucky_project, target, skip_web_module, selected_modules)
    
if __name__ == "__main__":
    build_main()
