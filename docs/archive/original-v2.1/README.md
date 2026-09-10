# 单摄像头四场景康复系统｜Codex实施包 v2.1

> 这是 2026-09-06 原始实施包的历史说明，其中“尚无 GUI”等表述只描述当时的材料。当前应用已在后续提交实现，请从 [项目首页](../../../README.md) 或 [文档索引](../../README.md) 进入。原 `MANIFEST.sha256.json` 对应原始包路径与内容，不是当前发布文件的校验清单。

**不等外接设备：笔记本内置摄像头先做，外接UVC摄像头到货后刷新选择；每次只跑一个场景、一路输入。**

本包替代上一版首周多摄像头＋雷达计划。核心仍是康复评估、训练指导和动作质量监督；配套是轻量活动任务和安全演示。

这不是可直接启动的完整桌面应用，而是**整合任务书＋配置模板＋设备/模型检查脚本＋部分纯逻辑参考及测试**。没有GUI成品、模型权重或真实用户录像。

## 交给Codex

先备份原工程和数据库，合并本包，不盲目覆盖同名源码。
阅读顺序：`../../specifications/SOFTWARE_SPEC.md` → `AGENTS.md` → `../../history/CHANGELOG.md` → `../../specifications/START_WITH_CODEX.md`。v1迁移历史仍在`MIGRATION_V1_TO_V2.md`。
不要同时把旧v1作为首周并行指令。旧RTSP/雷达需求已隔离在`../../plans/FUTURE_EXTENSIONS.md`。

`configs/`是待应用实现的自定义协议；不是复制进去就自动获得场景功能。`camera_reference.py`不是完整CameraManager，只示范匹配、坐标和运行上下文隔离。

## v2.1这次增加什么

把新资源资料筛成“本周使用、可选离线参考、后续研究”，没有新增必装模型或硬件。主规范补充骨架契约、原图/相对轨迹、指标有效性、动作完成和目标分离、多问题证据、经授权的调试导出及分层回归验证。

`../../plans/RESOURCES_AND_UPGRADES.md`是可选阅读，不是安装清单。本包不含研究权重、公开数据集、训练脚本或新成品业务逻辑。参考Python、配置与依赖沿用v2.0；本次主要更新Markdown文档，新增应用要求仍由Codex实现。

## 先列出本机摄像头

在目标Windows的独立环境中安装所需依赖后：

```powershell
python scripts/list_cameras.py --backend dshow
# DSHOW不合适时，明确换后端重新枚举，不沿用旧索引：
python scripts/list_cameras.py --backend msmf
```

列表行号是人机选择项，不是OpenCV索引。生产程序用相同backend枚举并配对打开；不把相机0写死。

## 检查真实姿态输入

先自行准备可信官方本地姿态权重，不自动下载。依赖按`requirements.in`在目标机安装并锁版本；PyTorch安装按实际CPU/GPU环境确定。

```powershell
# 列出设备后人工选择，不会默认开启0。
python scripts/smoke_pose.py --live --backend dshow --weights assets/models/yolo11n-pose.pt --device auto --display

# 选好后可保存单个设备引用。引用仅供匹配，不代表机位已通过验证。
python scripts/smoke_pose.py --live --backend dshow --weights assets/models/yolo11n-pose.pt --save-camera-ref data/my_camera.json --display

# 下次重新枚举匹配path+backend；找不到就要求重选，不换到别的摄像头。
python scripts/smoke_pose.py --camera-ref data/my_camera.json --backend dshow --weights assets/models/yolo11n-pose.pt --display

# 回放一律标记测试；此检查脚本不做业务计时，实际产品须用媒体时间。
python scripts/smoke_pose.py --video data/test.mp4 --weights assets/models/yolo11n-pose.pt --device cpu --display
```

脚本只做单路骨架接入检查，没有康复计数、场景切换、报警或报告。实际GUI由Codex按任务书完成。

## 自动检查

```powershell
python -m unittest discover -s tests -v
python scripts/list_cameras.py --help
python scripts/smoke_pose.py --help
```

测试通过范围见`VALIDATION.md`，不能当成实机热插拔、识别准确率或医学验证。

## 本周交付标准

选场景→选相机→预览→确认机位→执行任务→保存→重开报告。之后同一设备轮换剩余场景，切换时结束旧任务、释放设备、重新确认。未启用场景明确未监测，已有警报不被切换抹掉。

首周不必买新摄像头、雷达或计算盒。真实活动视野不足时明确限制结果；无外接相机不声称已完成USB切换实测。

## 来源与许可

主规范末尾列官方来源。未附模型权重、第三方整库、字体、示范视频或个人数据。Ultralytics、Qt与各权重许可分别核查。
