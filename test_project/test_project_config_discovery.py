#!/usr/bin/env python3
"""
测试 bucky_project 配置文件发现逻辑
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 添加 src 目录到 Python 路径
devkit_root = Path(__file__).parent.parent
sys.path.insert(0, str(devkit_root / 'src'))

from project import BuckyProject


class ProjectConfigDiscoveryTest(unittest.TestCase):
    def test_finds_config_in_src_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            src_dir = project_dir / 'src'
            src_dir.mkdir()

            config_path = src_dir / 'bucky_project.json'
            config_path.write_text('{"name":"demo","modules":{},"apps":{}}', encoding='utf-8')

            original_cwd = Path.cwd()
            try:
                os.chdir(project_dir)
                found_path = BuckyProject.get_project_config_file()
            finally:
                os.chdir(original_cwd)

            self.assertIsNotNone(found_path)
            self.assertEqual(found_path.resolve(), config_path.resolve())

    def test_relative_paths_follow_config_file_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir, tempfile.TemporaryDirectory() as other_dir:
            config_dir = Path(tmp_dir) / 'nested'
            config_dir.mkdir(parents=True)
            config_path = config_dir / 'bucky_project.json'
            config_path.write_text(
                '{"name":"demo","version":"0.1.0","base_dir":".","rust_target_dir":"target","modules":{"frontend":{"type":"web","name":"frontend","src_dir":"web/frontend"}},"apps":{"demo":{"name":"demo","rootfs":"rootfs/demo","default_target_rootfs":"deploy/demo","modules":{},"data_paths":[],"clean_paths":[]}}}',
                encoding='utf-8'
            )

            original_cwd = Path.cwd()
            try:
                os.chdir(other_dir)
                project = BuckyProject.from_file(config_path)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(project.base_dir.resolve(), config_dir.resolve())
            self.assertEqual(project.config_dir.resolve(), config_dir.resolve())
            self.assertEqual(project.rust_target_dir.resolve(), (config_dir / 'target').resolve())
            self.assertEqual(
                project.resolve_from_base_dir(project.modules['frontend'].src_dir).resolve(),
                (config_dir / 'web' / 'frontend').resolve()
            )
            self.assertEqual(
                project.resolve_from_config(project.apps['demo'].default_target_rootfs).resolve(),
                (config_dir / 'deploy' / 'demo').resolve()
            )

    def test_local_config_overrides_shared_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            config_path = config_dir / 'bucky_project.yaml'
            local_config_path = config_dir / 'bucky_project.local.yaml'
            config_path.write_text(
                '\n'.join([
                    'name: demo',
                    'version: 0.1.0',
                    'base_dir: .',
                    'rust_target_dir: shared-target',
                    'rust_env:',
                    '  RUSTFLAGS: shared',
                    '  SHARED: keep',
                    'modules:',
                    '  frontend:',
                    '    type: web',
                    '    name: frontend',
                    '    src_dir: web/frontend',
                    'apps: {}',
                ]),
                encoding='utf-8',
            )
            local_config_path.write_text(
                '\n'.join([
                    'rust_target_dir: local-target',
                    'rust_env:',
                    '  RUSTFLAGS: local',
                    '  LOCAL_ONLY: local-value',
                ]),
                encoding='utf-8',
            )

            project = BuckyProject.from_file(config_path, [local_config_path])

            self.assertEqual(project.name, 'demo')
            self.assertIn('frontend', project.modules)
            self.assertEqual(project.rust_target_dir.resolve(), (config_dir / 'local-target').resolve())
            self.assertEqual(project.rust_env['RUSTFLAGS'], 'local')
            self.assertEqual(project.rust_env['SHARED'], 'keep')
            self.assertEqual(project.rust_env['LOCAL_ONLY'], 'local-value')

    def test_finds_local_config_next_to_shared_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            config_path = config_dir / 'bucky_project.yaml'
            local_config_path = config_dir / 'bucky_project.local.yaml'
            config_path.write_text('name: demo\n', encoding='utf-8')
            local_config_path.write_text('rust_target_dir: local-target\n', encoding='utf-8')

            found_path = BuckyProject.get_project_local_config_file(config_path)

            self.assertEqual(found_path.resolve(), local_config_path.resolve())


if __name__ == '__main__':
    unittest.main()
