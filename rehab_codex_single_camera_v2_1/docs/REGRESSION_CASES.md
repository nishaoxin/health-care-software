# 固定回归集与真人验收记录规范

当前固定集为仓库中的自动测试，所有合成骨架 / 纯色视频均标记为逻辑或软件集成测试。没有真实人体动作录像及其人工标签，不能计算人体测角 MAE、问题 precision / recall、真实安全事件召回或误报率。

| 用例组 | 自动测试文件 | 主要期望 |
|---|---|---|
| 设备与生命周期 | test_app_camera.py、test_camera_reference.py | 刷新不打开输入、按 path/backend 重解析、无静默回退、停止失败锁定 |
| 时间 / 数据契约 | test_app_contracts.py、test_geometry.py | 关节顺序匹配、像素角度、缺点为空、保留全局下降、旧帧拒收 |
| 肩外展 / 坐站 | test_app_rehab.py | 计数终点、完整与目标分离、部分 / 中断保留、换人 / 遮挡不补计 |
| 指标 / 多问题 | test_app_rehab.py、test_app_contracts.py | 腕点缺失保留肩角，同时记录屈肘和侧倾，配置为快照 |
| 最小闭环 | test_app_controller.py | 合成来源预览 → 开始 → 动作 → 保存 → SQLite 重开，保存失败保护 |
| 活动 / 卧室 / 安全 | test_app_scenes.py | 缺测不计时、自报分离、排除区、低位分两种证据、未来帧不改旧事件 |
| 事件 / 存储 | test_app_storage.py | 已查看不等于关闭、重开仍保留事件、只读失败、异常退出不补造 |
| 桌面 UI | test_app_ui.py | 初始无默认相机、未确认不能开始、切模式中断、ROI 逆映射、隐私清屏 |
| 实际视频进程 | test_app_source_integration.py | 临时合成 AVI 实际编码 / 解码、回放预览边界、媒体时间、进程退出 |
| 实际姿态 SDK | test_app_vision_integration.py | 官方模型 CPU 空白帧推理、冻结 ByteTrack reset API、缺模型不下载 |
| 完整工作线程连接 | test_app_runtime_integration.py | 合成空白录像经真实采集进程、CPU 模型、质量层，确认无人时不开始、不生成假报告 |
| 分组与音频 | test_app_regression_audio.py | 按参与者 / 录像隔离、预测不作真值、旧上下文 / 缺音频不播放 |

新增真实样本时，给每段记录填写 case_id、匿名 participant_id、recording_id、source_kind、usage_context、来源 / 许可、机位、动作 / 侧别、规则 / 模型版本、人工标注者和时间来源。保留正常弯腰、正常坐下、床椅卧位、遮挡、低光、多人、出画与受控低位等困难负样本。

先按参与者和录制划分 `development` / `acceptance`，再切窗口或做缩放 / 镜像变体。同一参与者不能跨组，同一录像及其派生窗口不能跨组。`app/regression.py` 的 `validate_groups()` 校验此结构；标准标签必须声明 `annotation_origin=human`。

不要以模型输出决定标准答案；人工分歧单独记录。改规则后运行同一固定集；新增失败样本，不删除失败来改善显示的准确率。真正的最终验收需使用没有参与调阈值的人 / 录制条件，并分别报告有效观察覆盖和拒测比例。
