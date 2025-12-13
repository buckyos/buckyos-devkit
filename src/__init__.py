"""
BuckyOS DevKit - Shared development script library for BuckyOS

Contains tools for building, installation, remote management, etc.
"""

__version__ = "0.1.0"

# Import core components for external use
from .cert_mgr import CertManager
from . import buckyos_kit
from . import cert_mgr

# Import project configuration
from .project import (
    BuckyProject,
    AppInfo,
    WebModuleInfo,
    RustModuleInfo
)

from .install import install_app_data, reinstall_app, update_app, clean_app
from .build import build

# Export main components
__all__ = [
    # Version
    '__version__',
    
    # Certificate management
    'CertManager',
    
    # BuckyOS kit utilities
    'buckyos_kit',
    
    # Project configuration
    'BuckyProject',
    'AppInfo',
    'WebModuleInfo',
    'RustModuleInfo',
    
    # Installation
    'install_app_data',
    'reinstall_app',
    'update_app',
    'clean_app',
    
    # Build
    'build',
]
