# 康复助手应用目录

这里是当前可运行应用的代码与运行资源，当前版本见 [app/__init__.py](app/__init__.py)。目录名称沿用原实施包名称，避免改变现有虚拟环境和本地数据位置。

- 打开软件：在项目根目录双击 `启动康复助手.cmd`。
- 使用与安装：[项目说明](../README.md)、[使用指南](../docs/USER_GUIDE.md)。
- 开发与验证：[开发说明](../docs/DEVELOPMENT.md)、[当前交接与待办](../docs/HANDOFF.md)。
- 原任务书与历史验收：[文档索引](../docs/README.md)。

| 目录 / 文件 | 用途 |
| --- | --- |
| `app/` | 采集、姿态、动作、训练、存储与 PySide6 界面 |
| `assets/` | 图标、提示音、导航插图、模型来源清单；模型文件仅在本地准备 |
| `configs/` | 应用模板与动作 / 场景规则 |
| `scripts/` | 环境准备、设备枚举、模型检查、分批回归和界面检查 |
| `tests/` | 软件逻辑、合成流程、模型与回放集成测试 |
| `requirements.lock.txt` | 主环境的固定依赖 |
| `requirements.landmarks.lock.txt` | 可选关键点进程的固定依赖，单独安装 |
| `camera_reference.py`、`geometry_reference.py` | 原始参考模块，保留兼容与参考测试 |
| `.venv/`、`.venv-landmarks/` | 本机运行环境，Git 忽略 |
| `data/` | 当前电脑的个人档案、会话与偏好，Git 忽略 |
| `.runtime/`、`qa-output/` | 日志、下载缓存及生成的测试证据，Git 忽略 |
