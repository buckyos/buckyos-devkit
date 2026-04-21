from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import build_rust


def _mock_which_factory(resolved_tools):
    def _mock_which(name):
        return resolved_tools.get(name)

    return _mock_which


class BuildRustMuslToolchainTests(unittest.TestCase):
    def test_x86_64_musl_prefers_triplet_toolchain(self):
        with patch.object(build_rust, "get_host_target", return_value="x86_64-unknown-linux-gnu"):
            with patch.object(
                build_rust.shutil,
                "which",
                side_effect=_mock_which_factory(
                    {
                        "x86_64-linux-musl-gcc": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-gcc",
                        "x86_64-linux-musl-g++": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-g++",
                        "x86_64-linux-musl-ar": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-ar",
                        "x86_64-linux-musl-ranlib": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-ranlib",
                        "musl-gcc": "/usr/bin/musl-gcc",
                        "musl-g++": "/usr/bin/musl-g++",
                        "musl-ar": "/usr/bin/musl-ar",
                        "musl-ranlib": "/usr/bin/musl-ranlib",
                    }
                ),
            ):
                env_vars = build_rust.get_cross_compile_env_vars_by_target("x86_64-unknown-linux-musl")

        self.assertEqual(
            env_vars,
            {
                "CC_x86_64_unknown_linux_musl": "x86_64-linux-musl-gcc",
                "CXX_x86_64_unknown_linux_musl": "x86_64-linux-musl-g++",
                "AR_x86_64_unknown_linux_musl": "x86_64-linux-musl-ar",
                "RANLIB_x86_64_unknown_linux_musl": "x86_64-linux-musl-ranlib",
                "CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER": "x86_64-linux-musl-gcc",
            },
        )

    def test_aarch64_musl_populates_complete_toolchain(self):
        with patch.object(build_rust, "get_host_target", return_value="x86_64-unknown-linux-gnu"):
            with patch.object(
                build_rust.shutil,
                "which",
                side_effect=_mock_which_factory(
                    {
                        "aarch64-linux-musl-gcc": "/opt/aarch64-linux-musl-cross/bin/aarch64-linux-musl-gcc",
                        "aarch64-linux-musl-g++": "/opt/aarch64-linux-musl-cross/bin/aarch64-linux-musl-g++",
                        "aarch64-linux-musl-ar": "/opt/aarch64-linux-musl-cross/bin/aarch64-linux-musl-ar",
                        "aarch64-linux-musl-ranlib": "/opt/aarch64-linux-musl-cross/bin/aarch64-linux-musl-ranlib",
                    }
                ),
            ):
                env_vars = build_rust.get_cross_compile_env_vars_by_target("aarch64-unknown-linux-musl")

        self.assertEqual(
            env_vars,
            {
                "CC_aarch64_unknown_linux_musl": "aarch64-linux-musl-gcc",
                "CXX_aarch64_unknown_linux_musl": "aarch64-linux-musl-g++",
                "AR_aarch64_unknown_linux_musl": "aarch64-linux-musl-ar",
                "RANLIB_aarch64_unknown_linux_musl": "aarch64-linux-musl-ranlib",
                "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER": "aarch64-linux-musl-gcc",
            },
        )

    def test_x86_64_musl_missing_cxx_raises_clear_error(self):
        with patch.object(build_rust, "get_host_target", return_value="x86_64-unknown-linux-gnu"):
            with patch.object(
                build_rust.shutil,
                "which",
                side_effect=_mock_which_factory(
                    {
                        "x86_64-linux-musl-gcc": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-gcc",
                        "x86_64-linux-musl-ar": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-ar",
                        "x86_64-linux-musl-ranlib": "/opt/x86_64-linux-musl-cross/bin/x86_64-linux-musl-ranlib",
                        "musl-gcc": "/usr/bin/musl-gcc",
                        "musl-ar": "/usr/bin/musl-ar",
                        "musl-ranlib": "/usr/bin/musl-ranlib",
                    }
                ),
            ):
                with self.assertRaises(RuntimeError) as exc_info:
                    build_rust.get_cross_compile_env_vars_by_target("x86_64-unknown-linux-musl")

        message = str(exc_info.exception)
        self.assertIn("musl-tools is only enough for pure C builds.", message)
        self.assertIn("x86_64-linux-musl-g++", message)
        self.assertIn("musl-g++", message)

    def test_apply_darwin_linux_cross_compile_env_sets_bindgen_and_cxxflags(self):
        env = {
            "CC_x86_64_unknown_linux_musl": "x86_64-linux-musl-gcc",
            "CXX_x86_64_unknown_linux_musl": "x86_64-linux-musl-g++",
            "BINDGEN_EXTRA_CLANG_ARGS": "--existing",
            "CXXFLAGS": "-O2",
        }
        with patch.object(
            build_rust,
            "_bindgen_args_for_linux_target",
            return_value=["--target=x86_64-unknown-linux-musl", "--sysroot=/opt/cross/sysroot"],
        ):
            with patch.object(build_rust, "_toolchain_has_linux_headers", return_value=True):
                build_rust._apply_darwin_linux_cross_compile_env(env, "x86_64-unknown-linux-musl")

        self.assertEqual(
            env["BINDGEN_EXTRA_CLANG_ARGS"],
            "--existing --target=x86_64-unknown-linux-musl --sysroot=/opt/cross/sysroot",
        )
        self.assertEqual(
            env["BINDGEN_EXTRA_CLANG_ARGS_x86_64_unknown_linux_musl"],
            "--target=x86_64-unknown-linux-musl --sysroot=/opt/cross/sysroot",
        )
        self.assertEqual(env["CXXFLAGS"], "-O2 -include cstdint")
        self.assertEqual(env["CXXFLAGS_x86_64_unknown_linux_musl"], "-include cstdint")
