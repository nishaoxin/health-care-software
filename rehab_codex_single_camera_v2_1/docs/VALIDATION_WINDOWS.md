# Windows 工程首版验收记录

## 2026-09-08 · 功能优先：53 项任务与本轮评估清单

五批互不重叠的工程检查，共 **673 项与 4 个子测试通过**。没有反复启动全量检查；被排除的模型/回放实测明确保留为本轮未复测。

| 批次 | 实际命令中的测试文件 | 结果 |
| --- | --- | --- |
| 新增动作 | `test_axial_and_extension.py` | 110 项通过，9.47 秒；已确认进程正常退出 |
| 原几何与核心流程 | `test_app_joint_exercises.py test_app_assessment.py test_app_controller.py test_training_execution.py` | 220 项与 4 个子测试通过，4.49 秒 |
| 注册、界面入口与关键点协议 | `test_product_catalog.py test_product_body_overview.py test_app_ui.py test_training_ui.py test_app_landmarks.py` | 264 项通过，4.37 秒；仅排除 3 项 `test_official_local_models_really_load_on_blank_image_without_false_person` |
| 清单与数据库 | `test_assessment_batches.py test_assessment_batch_ui.py test_participants.py test_app_storage.py` | 51 项通过，2.16 秒 |
| 原扩展路径与运行层 | `test_app_joint_expansion_flow.py test_app_runtime_integration.py test_training_runtime.py test_training_feedback.py` | 28 项通过，3.90 秒；排除 3 项 `routes_single_blank_replay` 和 1 项 `actual_blank_replay` |

以上用项目 `.venv/Scripts/python.exe -m pytest ... -q` 执行。被排除的 7 项涉及此前重复加载的本地模型/真实空白回放；本次没有换模型、更新依赖或修改采集后端，未把旧验证结果当成本轮已复测。

- 新增动作验证：已知坐标角度、左右侧、等比例平移缩放、镜像方向、刚性旋转、缺少必要点、短参考线拒测、手指反向起点与减小方向目标；40 条左右侧合成流程通过真实 SceneController/SQLite 完成评估→保存→汇总→训练两组。不是人体模型准确度或临床疗效验证。
- 清单验证：只关联本轮项目，异人/异来源拒绝、旧成功不填入、最新失败需补测、异常退出、跳过/恢复/冲突/结束/重开/删除报告后状态、开始前重新校验、运行期间禁止修改、失败保留选择。真实 Runtime 读写清单不打开输入。
- 数据迁移：v1/v2→v3 迁移前备份、旧会话不改写、备份失败原库不变、只读旧库不迁移。测试仅使用临时数据库，没有为测试打开正式用户数据。
- 实际应用入口 `app.main --data-dir qa-output/function-v05-data --screenshot qa-output/function-v05-startup.png` 正常退出；独立 QA 数据目录，无摄像头采集。仅验证初始化与关闭，不开展视觉重设计。
- `compileall` 与 `git diff --check` 通过。开发中一项旧 UI 测试仍断言手指只有 14 个任务；扩展为 28 个正/反起点任务后同步该期望，相关批次已通过，原动作逻辑未删减。
- 本轮仍未验证真人测角/计数精度、临床适用性、内置/USB 相机切换或长期实机运行。肩/髋旋转、前臂旋转、拇指 CMC/对掌等未实现范围见 `FUNCTIONAL_EXPANSION_V0_5.md`。

## 2026-09-08 · 训练组次、休息、暂停与结束反馈

- 当前分批检查：`tests/test_training_execution.py tests/test_app_controller.py tests/test_training_runtime.py` 共 39 项与 4 个子测试通过（2.23 秒）；`tests/test_training_ui.py tests/test_training_feedback.py tests/test_product_navigation.py tests/test_participant_runtime.py` 共 31 项通过（4.15 秒）。两批均正常退出，没有放宽等待阈值。
- 覆盖计划驱动、组间不计次、空休息配置、暂停中断、坐站最后一次与未观察回坐、迟到/非有限时间、恢复确认、识别失败后旧结果清除、保存失败恢复、手工感受空值/0/冲突/删除后拒写、导出及小窗口操作。
- 新增真实 Runtime/SQLite 命令往返：结束记录→填写感受→重开报告→正常退出→数据库重开；使用明确 SYNTHETIC/TEST 临时记录，不打开相机、不运行姿态推理。
- 此前训练开发中的一次全量结果为 **554 项通过、1 项失败**（38.09 秒），失败为 `test_actual_blank_replay_has_no_person_no_task_and_no_false_save` 等待观察超时。该文件原样单独重跑 3 项通过（3.79 秒）；根因尚未证实。本次按用户要求不重复整套模型检查，不宣称当前全量通过。
- `scripts/qa_training.py` 使用实际 PySide 控件、生产命令处理、SceneController 和 SQLite 配合合成姿态夹具，走通训练、暂停、确认恢复、休息、下一组、结束、填写感受与重开报告。不是实时 Runtime 线程/真人模型验证。截图放在忽略目录 `qa-output/training/`；已查看 1100×730 固定训练栏、结束反馈与计划表单。
- 真人准确度、患者适用性、相机实机恢复和长期连续运行仍未验证。没有安装新依赖、下载模型或修改用户数据库结构。

## 2026-09-08 · 本地个人档案

- 新增个人信息保存/重开、旧编号发现、空值与来源、版本冲突、迁移前备份及备份失败、只读 v1、导出脱敏测试。
- 新增 UI 新建/切换、保存失败草稿保留、运行/待保存门禁、预览停止后编辑、同名区分、长文本与两种窗口尺寸测试；真实 Runtime 的新建和重开不打开相机。
- 新增任务开始时个人信息快照测试：修改档案不影响旧报告，不自动修改训练幅度或陪同设置。
- 最终全量 `python -m pytest -q`：523 项测试与 4 个子测试通过（25.70 秒）；`compileall` 和 `git diff --check` 通过。
- `python scripts/qa_participants.py`：实际 PySide 窗口通过真实 Runtime/SQLite 走通新建→保存→身体档案→关闭→重开；在独立临时目录测试，无真人资料、无正式测量、无相机采集。截图在忽略目录 `qa-output/participants/`，已查看表单、1100×730 档案页和重开页。
- 本次未测试真人精度、患者适用性、USB 热插拔或长期现场使用。训练组间执行、更多关节方向、动作示意与完整产品验收仍未完成。

## 2026-09-08 · 应用 v0.4 第一阶段：原生界面与动作入口

本次保留主环境、可选模型和原测量定义，不迁移或清空用户数据库。完整产品目标仍在进行，详见 `PRODUCT_COMPLETION_PLAN.md`。

| 检查 | 实际结果 | 证明范围 |
| --- | --- | --- |
| 全量 pytest | 486 项通过，另有 4 个子测试，26.63 秒 | 原测量/模型协议/来源/存储回归，以及本次新增内容、动作库、档案与界面门禁 |
| 动作说明 | 33 项逐一通过内容契约，包含具体手指关节和四个腕部方向 | 摆位、拍摄、起点、出程、回程、计次、测量边界完整；不代表临床有效性 |
| 动作库交互 | Qt 鼠标点击、部位筛选、多个关键词搜索、未知动作与空结果检查通过 | 真实控件选择实际注册动作，不打开摄像头，不更改测量定义 |
| 档案与训练 | 空/可用/缺测状态，筛选清空选择，异用户响应隔离通过 | 选中无效记录不能借用另一行可用评估开始训练；仍可打开缺测报告 |
| 生命周期显示 | 保存失败按钮、未确认训练、旧观察状态、断开后的旧帧处理通过 | 不宣称未确认计划可以开始，不以旧画面显示在线，不丢弃待保存结果 |
| 原生布局 | 1100×730、1360×900、1600×1000 离屏渲染，检查动作库/手指/准备页/输入设置；另查档案、关联训练、保存失败 | 最小窗口尺寸可保持，底部操作可用，小窗口内容可滚动；非摄像头实测 |
| 实际应用入口 | `app.main --data-dir qa-output/product-v04-final-data --screenshot qa-output/product-v04-startup-final.png` 正常退出 | 独立测试数据目录初始化、默认动作库、窗口关闭，不接触用户数据 |
| 静态检查 | compileall、git diff --check 通过 | 语法与补丁格式 |

复现：`.venv/Scripts/python.exe -m pytest -q`、`.venv/Scripts/python.exe scripts/qa_product.py`、`.venv/Scripts/python.exe scripts/qa_desktop.py`。QA 文件只在忽略的 `qa-output/` 下，样本标为 SYNTHETIC / TEST，不上传或混入正式数据。

开发中发现并修复了窄面板确认项宽度、默认动作库导致的旧测试准备步骤、保存失败时的错误重开提示、离线时旧状态覆盖提示。保留原行为测试，未通过降低旧测量门槛使测试变绿。

后续仍须完善本地个人档案、训练计划执行、动作示意及更多关节方向；真人精度、患者适用性、USB 热插拔和真人连续运行本轮未验证。

---

## 2026-09-08 · 应用 v0.3 扩展关节

本次 Windows x64 / Python 3.13.12，主 `.venv` 保留，可选 `.venv-landmarks` 使用 MediaPipe 1.0.1。以下是本次结果；后文为历史记录。

| 检查 | 实际结果 | 能证明的范围 |
|---|---|---|
| 全量 pytest | 432 项通过，另有 4 个子测试通过，26.84 秒 | 原回归、新模型协议、14 个手指关节独立几何、腕/踝/肩/髋方向、全部新增动作计数、数据/界面流程 |
| unittest | 165 项通过，10.234 秒 | 与上行重叠的 unittest 子集；参数化测试仍由 pytest 执行，不相加 |
| 官方模型真实加载 | Pose33、Hand21、Pose33+Hand21 腕组合均实际启动并对纯色 RGB 输入推理，返回 0 个目标 | 本机模型/接口/CPU/退出可用，不是人体识别准确度 |
| Runtime 扩展后端路由 | 踝、手指、腕分别通过同一个 CameraManager 从临时纯色 AVI 解码并送到正确的真实模型；不生成会话或假报告 | 原采集/推理框架接入，明确 REPLAY_FILE + TEST；不是摄像头实机 |
| 保存与训练 | 16 个左右侧扩展合成闭环及 2 个校准门禁测试通过 | 评估保存、身体信息、训练引用、SQLite 重开、普通导出无骨架；旧/伪造基线和缺方向被拒绝 |
| 独立环境 | 两个环境 pip check 均无冲突；`setup_landmarks.ps1 -VerifyOnly` 通过 | 原环境未混装可选 OpenCV；模型 SHA256 与官方固定版本清单一致 |
| 桌面布局 | 原场景与新增髋、腕、踝、手指、身体汇总和关联训练离屏渲染并检查 | `qa-output/` 的界面自有状态；无用户屏幕、摄像头或用户数据库采集 |
| 完整入口 / 静态检查 | `app.main --data-dir .runtime/qa-v03-startup --screenshot qa-output/startup-v03.png`、compileall、git diff --check 通过 | 独立测试数据目录初始化、离屏启动与关闭；没有打开摄像头 |

运行记录：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts/qa_desktop.py
.\scripts\setup_landmarks.ps1 -VerifyOnly
.\.venv\Scripts\python.exe -m pip check
```

新模型协议保留 Hand21 逐点置信度为 null。已测试缺点、零长骨段、旧上下文、双手不匹配、进程响应超时/取消、错误序号关闭自有模型进程；这些检查不能自动识别全部遮挡和离面运动。

首轮扩展开发测试发现语法括号遗漏、浮点时间边界和过短的手部测试骨段，已分别修复语法、时间容差和测试样本后重跑。原测试的六项/十二项固定数量断言随新注册表更新，原行为测试没有移除。

尚未完成新增动作的真人可见性检查、独立人工量角误差、患者动作适用性、USB 热插拔或真实视频 30 分钟连续运行。腕/踝/手指必须保持“实验性二维观察”；“已评估”只说明有可追溯观察数据，不表示临床验证通过。

---

## 2026-09-08 · 应用 v0.2 评估与训练扩展

当前验证环境为 Windows x64、项目 `.venv`、Python 3.13.12。以下是本次实际执行结果；后面的 2026-09-06 记录保留为历史，不代表本次测试状态。

| 检查 | 结果 | 证据范围 |
|---|---|---|
| 全量 pytest | 265 项通过，另有 4 个子测试通过，10.88 秒 | 含原回归、102 项关节测试、35 项身体汇总/报告测试及新增流程保护 |
| unittest 回归 | 163 项通过，9.430 秒 | unittest 类测试；另外 102 项关节参数化测试由上行 pytest 执行，不重复相加 |
| 新动作 | 肩前屈、肘屈伸、坐位膝屈伸、髋外展的几何/状态机/必要指标校验通过 | 合成骨架和已知几何，不是真人准确度 |
| 评估到训练 | 保存评估、重建身体汇总、训练前校验、引用快照及重开通过 | 同人/侧别/动作/来源情境隔离；目标不自动填写；删除评估会拒绝启动 |
| 桌面流程 | 模式分栏、切换用户/侧别清空目标、保存失败不跳汇总、迟到旧画面拒收通过 | Qt 控件自动测试 |
| 桌面布局 | 评估、训练、空身体信息、合成身体汇总、关联训练、计划对话框与其他场景离屏渲染并检查 | `qa-output/` 生成图；样本明确 SYNTHETIC/TEST，不读取用户数据库或摄像头 |
| 完整入口 | `app.main --data-dir .runtime/qa-v02-startup --screenshot qa-output/startup-v02.png` 正常退出 | 独立测试目录、真实应用初始化和关闭，无相机采集 |
| 语法与依赖 | compileall、pip check、git diff --check 通过 | 没有新增依赖或模型 |

首轮 unittest 的真实空白回放集成曾等待姿态结果超时；未修改生产超时或放宽测试阈值，单独重跑通过，随后全量 pytest 通过。新增四项动作尚未完成真人动作与独立人工量角对照、受限活动度适用性或临床验证；不能以自动测试宣称治疗效果或全部代偿识别通过。

本次不修改数据库结构、不清空历史数据。肩动作保留已设阈值下的屈肘/躯干投影倾斜提示；新增肘、膝、髋仅提供测量、往返计数与人工目标指导，暂不判定支撑稳定性或全部代偿。

---

日期：2026-09-06。目标工作区：用户本机 Windows x64；环境为项目 `.venv` / Python 3.13.11。下列记录只陈述已执行的内容。

## 已完成的软件内容

- 新增 PySide6 Widgets 桌面应用、四场景切换、实时相机 / 本地回放选择、人工机位确认与矩形 ROI 编辑。
- 输入由 CameraManager 拥有的单一采集进程打开；推理在单独工作线程串行运行，界面线程不做采集或模型推理。
- 肩外展与坐站状态机、个人目标、逐指标有效性、多问题证据、训练文本反馈与本地提示音。
- 活动有效时间积分、久坐提醒、站立 / 步行任务、延期 / 拒绝 / 自报分离；床区和低位事件的受控规则演示。
- SQLite 单一写入线程、配置快照、停止保存、报告重开、HTML / JSON / CSV 导出、明确授权的骨架导出。
- 旧上下文拒收、相机释放、隐私暂停、保存失败恢复、显式丢弃留痕、人工事件状态转换、异常退出记录及同数据目录实例锁。

## 实际执行

| 检查 | 当前结果 | 能证明的范围 |
|---|---|---|
| 原包参考测试 | 41 项通过，包含在全量测试中 | 原参考几何 / 匹配 / 配置约束 |
| 全量应用测试 | pytest：109 项通过，6.15 秒；unittest：109 项通过，6.029 秒，原始输出随文保存 | 纯逻辑、合成闭环、存储、Qt 交互、本地视频进程与 CPU SDK 接入 |
| CPU 姿态推理 | 官方 yolo11n-pose.pt 对空白 640×480 帧成功推理，输出 0 人 | 模型加载与 CPU 路径；不代表人体识别通过 |
| ByteTrack 重置 | 冻结 8.3.199 SDK 的实际 tracker.frame_id 在新上下文回到 1 | 本次版本跟踪重置接口 |
| 本地回放进程 | 临时合成 AVI 经过真实 OpenCV 编码 / 解码；预览与开始分界、媒体时长和退出验证 | 文件输入和进程生命周期；不代表摄像头实测 |
| 桌面图像检查 | 四场景、空历史、计划对话框离屏渲染并检查；修复字体、复选框、下拉箭头问题 | 界面布局与交互，不是真人视频画面 |
| 本机启动入口 | 从根目录 Start-Rehab.ps1 启动应用，进程保持运行；启动日志无报错 | 当前独立环境的桌面启动，不包含真实相机或真人动作验收 |
| 设备枚举 | DSHOW 得到 1 条 HD Webcam，当前 index 0，path 存在 | 仅枚举；未因 index 为 0 自动打开 |
| 依赖检查 | pip check 无依赖冲突；44 个 wheel 官方 PyPI SHA256 核对通过 | 版本一致性与下载文件来源一致 |
| 模型来源 | 官方 ultralytics/assets v8.3.0；SHA256 869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0 | 此次准备的模型文件身份 |

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/qa_desktop.py
.\.venv\Scripts\python.exe scripts/list_cameras.py --backend dshow
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/verify_wheels.py
```

首次直接使用系统 Python 运行原参考测试时缺 PyYAML；此后在项目独立环境中安装并通过，不修改系统环境。早期 Qt 绘制的 QPen 参数和离屏字体问题已经修复并重跑。最初官方下载速度缓慢，改用镜像取得依赖后逐项校验官方 hash。

## 未实测 / 未交付的部分

- 没有打开用户摄像头录制或分析真人动作；本机相机预览表现、完整人体动作闭环和实测图像质量仍待操作者使用验证。
- 未进行内置 → 外接 → 内置、USB 拔插、权限被拒和占用场景的真实硬件测试。FakeWorker 只验证软件保护分支。
- 尚无独立人工标签录像；测角误差、计数准确率、质量规则 precision / recall / F1、真实低位 / 安全事件误报漏报与触发延迟均未验收。
- 未完成目标机带真实视频的 30 分钟持续运行或四场景真人往返演示。
- 机位主要依赖人工确认；未实现或验证精确自动视角 / 机位移动判断。旋转、裁剪、自动三维校准不提供。
- 未提供经复核的真人动作示范视频、语音医疗指导、原始视频 / 截图录制或免 Python 安装包。界面明确标待配置或未启用；本地非语言提示音已提供。
- 未做患者使用或临床验证，没有证据可宣称诊断、治疗效果或全天安全监护可靠性。

## 操作者最后验收路径

在当前启动入口打开应用 → 选择 HD Webcam → 预览确认彩色画面与视野 → 肩外展及指定侧 → 人工确认机位 → 在允许的舒适范围做任务 → 停止保存 → 关闭再打开历史报告。

在已有授权真人录像前，自动测试只能对软件逻辑作结论。遇到错误先定位采集、骨架、几何、阶段、规则还是保存，再修对应层，不下载另一套研究框架替代本次验证。
