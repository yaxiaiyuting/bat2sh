"""Android 入口点（pyside6-android-deploy 要求主入口命名为 main.py）。

桌面入口是 python/bat2sh/__main__.py；Android 打包后源码目录不在默认
sys.path 上，因此这里显式加入当前目录再做一层薄封装。

注意：本文件是 Android 打包的**第一项硬性要求**，但当前**未完成 APK 构建** ——
上游未提供与 PySide6 6.11.x 匹配的 Android wheel，详见同目录 README.md。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bat2sh.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
