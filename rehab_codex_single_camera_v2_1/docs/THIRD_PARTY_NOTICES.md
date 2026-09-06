# 第三方来源与许可记录

本文件记录实际使用资源，不表示取得了额外商业授权。未向外发布软件或数据。

| 资源 | 本次实际版本 / 来源 | 许可记录与范围 |
|---|---|---|
| Ultralytics | 8.3.199，PyPI 官方发行内容 | 官方为 AGPL-3.0 / Enterprise 路线；未声称拥有 Enterprise 授权 |
| YOLO11n-pose | 官方 ultralytics/assets v8.3.0 发行附件 | 同上；精确地址、hash、骨架契约在 assets/models/manifest.json |
| PyTorch / torchvision | 2.9.1 / 0.24.1；本机 torch 报告 2.9.1+cpu，CUDA build 为 None | BSD 类许可；实际 wheel 元数据见依赖清单 |
| Qt for Python / PySide6 | Essentials 6.11.2 + shiboken6 6.11.2 | 使用 Qt Widgets 子集；按实际模块核查 LGPLv3 / GPLv3 / 商业路线 |
| OpenCV | opencv-python 4.12.0.88 | 主项目 Apache-2.0；wheel 中附带组件也有各自许可 |
| 摄像头枚举 | cv2-enumerate-cameras 1.3.3 | 项目 MIT 许可，按官方仓库显式配对 backend + index |
| NumPy / PyYAML / pytest 等 | requirements.lock.txt 中固定版本 | 安装 wheel 的官方来源、hash、许可元数据分别记录 |
| 本地提示音 / 图标 | 本次自行生成的非语言 WAV 和 SVG | 无第三方录音、照片或图标素材；提示音不含医疗语音 |
| 字体 | Windows 系统已有 Microsoft YaHei / Segoe UI | 运行时引用；未把系统字体复制或分发进项目 |
| 测试视频 | 测试时用代码生成纯色图像并编码为临时 AVI | 明确合成内容；不属于真实人体动作验证 |
| 人体录像 / 数据集 / 示范视频 | 未提供、未下载、未打包 | 没有患者录像或公开研究数据授权的推定 |

依赖通过清华 PyPI 镜像取得以改善下载速度，随后将 **44 个 wheel 的 SHA256 与官方 pypi.org 发行元数据逐一核对**。核对程序为 `scripts/verify_wheels.py`，逐文件记录在 `DEPENDENCY_MANIFEST.json`。模型直接来自官方 GitHub 发行附件，独立核对 hash。

官方参考：

- [Ultralytics YOLO11 与模型文件名](https://docs.ultralytics.com/models/yolo11/)
- [姿态输出与 COCO17 定义](https://docs.ultralytics.com/tasks/pose/)
- [跟踪接口](https://docs.ultralytics.com/modes/track/)
- [Ultralytics 许可](https://www.ultralytics.com/license)
- [Qt for Python 许可](https://doc.qt.io/qtforpython-6/licenses.html)
- [Qt 工作线程](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)
- [PyTorch 安装选择器](https://pytorch.org/get-started/locally/)
- [cv2-enumerate-cameras 官方仓库](https://github.com/lukehugh/cv2_enumerate_cameras)

Ultralytics 的代码、权重以及其训练数据背景是不同的权利对象；资源名称出现在任务书中不等于取得使用许可。未来分发或商用前，需要按实际组合履行第三方义务并确定本项目自身的分发许可。
