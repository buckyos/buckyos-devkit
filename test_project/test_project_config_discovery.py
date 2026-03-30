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


if __name__ == '__main__':
    unittest.main()
