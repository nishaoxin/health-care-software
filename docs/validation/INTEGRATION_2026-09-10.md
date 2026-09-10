# 2026-09-10 压缩包整合与本机验收

本记录针对应用 0.9.2 的目录整理、运行环境恢复和软件验证。真人准确度与双摄实施不属于已经取得的证据。

## 输入与版本关系

- 用户提供文件：`health-care-software-main.zip`，623892605 字节。
- SHA256：`62498fac9d454bc40f00a2fa2ade12171f11d7caf38feb5231abd27419b1e2c7`。
- 整理前本地与 GitHub `main`：`d17b672aee4db8f0a78e7d84085a12548e5728e0`。
- 压缩包 Git `main`：`552fa2a42b205e89055d5ada0701b2cedd8c309a`，为前者之后的 12 个连续提交。
- 压缩包源码与其 Git 提交一致，没有待提交修改或合并冲突；原历史对象完整性检查通过。本次按连续历史接入，没有覆盖原仓库的 `.git` 配置或历史。
- 归档分类、29 份文档的迁移映射和 12 个提交见[整合清单](results/2026-09-10-import.json)。

## 整理方式

- 根目录集中启动、环境准备和总说明；应用代码、模型清单、配置、测试及本地环境位置保留。
- 使用文档、当前交接、开发说明集中在 `docs/`；规格、版本历史、长期计划、验收和依赖来源各有目录。
- 原始任务书和参考测试资料归档到 `docs/archive/original-v2.1/`；旧的 109 项测试输出保留为历史，不用作本次结果。
- 完整压缩包移入 `backups/incoming/`；其 35817 个环境文件、个人数据库、缓存和运行证据不进入 Git。
- 当前电脑原有数据在整理前备份并保留；没有导入同学的个人档案或评估数据库。
- 统一应用版本与侧栏版本为 0.9.2。没有在本次整理中修改动作角度定义、计数阈值或开启第二路摄像头。

## 本机验证

### 环境与模型

- Windows x64，主环境 Python 3.13.11。保留本机原 `.venv`，`pip check` 通过；没有执行一次全新主环境安装。
- 新建隔离的 `.venv-landmarks`，固定 MediaPipe 1.0.1。官方源下载过慢后，显式使用清华镜像下载 19 个固定版本 wheel，逐个与官方 PyPI JSON 中的 SHA256 对照，再从本地 wheel 安装；[校验清单](../dependencies/LANDMARK_DEPENDENCY_MANIFEST.json)中的 19 项均通过。
- Pose / Hand 模型从来源清单内的 Google 官方地址取得，hash 与已固定的 `landmarks-manifest.json` 一致。`setup_landmarks.ps1 -VerifyOnly` 的依赖、版本和模型校验通过；两套环境没有混装。
- 根目录安装包装脚本及应用安装脚本共 5 份 PowerShell 文件通过语法解析。Python `app`、`scripts`、`tests` 通过 `compileall`。

### 首轮失败、定位和修复

首轮完整检查在扩展动作集成组遇到 3 项失败：腕、踝和手指的空白录像没有返回模型结果；当时停止了后续批次，[初始结果](results/2026-09-10-initial.json)保留失败事实。

进一步用相同本地模型、相同空白帧，只改变模型目录，得到 3 个英文路径成功、3 个中文含空格路径失败。错误来自 MediaPipe 原生文件路径加载。新增的对照回归覆盖 Pose、Hands、Wrist 三个后端；[修复前对照](results/2026-09-10-unicode-before.json)保留各例结果。

修复为由 Python 读取模型，将核对 SHA256 的同一份字节通过 `model_asset_buffer` 交给 MediaPipe。没有更换模型、放宽可见性或改动角度 / 计数规则。修复后 6 个路径用例全部通过，腕 / 踝 / 手指实际模型进程与空白回放路径也全部通过。

### 修复后完整回归

在应用目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\check_project.py --output .runtime\checks\integration-20260910-final
```

43 个测试文件分成 9 个互不重复的批次，**1102 项主测试与 4 项子测试通过，0 失败、0 错误、0 跳过**。包含进程启动和汇总的总耗时约 74 秒；逐批耗时和文件列表见[最终结果](results/2026-09-10-final.json)。JUnit 的 `tests=1106` 含这 4 项子测试，不再额外相加。

| 批次 | pytest 实际通过数 |
| --- | ---: |
| core | 546，另 4 项子测试 |
| ui | 341 |
| test_app_joint_expansion_flow | 21 |
| test_app_landmarks | 179 |
| test_app_runtime_integration | 3 |
| test_app_source_integration | 1 |
| test_app_vision_integration | 2 |
| test_camera_test_integration | 3 |
| test_model_paths_integration | 6 |

原始日志、JUnit、故障定位脚本保留在本地 `.runtime/checks/`；上传的是结果摘要，未上传临时数据和运行日志。

### 界面与实际启动

- `qa_body_camera_ui.py`：1100×730、1360×900、1600×1000 的身体导航及相机连接 / 错误布局通过。
- `qa_neck_shoulder.py`：肩内收起点、头颈缺点提示、1100×730 与 1360×900 大字指导布局通过。
- `qa_training.py`：合成骨架经实际动作逻辑和命令分发，完成训练、暂停、恢复、组间休息、结束反馈、SQLite 保存和报告重开。
- `qa_participants.py`：独立临时数据库中的用户新建、保存、选择、身体档案和关闭重开通过。
- 使用真实 `app.main` 入口、独立 `qa-output/integration-20260910/startup-data` 和离屏模式启动，截图后正常退出。已目视检查首页、小窗口肩部导航、大字缺点提示和训练休息布局；[首页截图](../images/home.png)没有个人档案或相机画面。
- 相对 Markdown 链接检查通过。普通启动、安装和验证入口均已更新到整理后的路径。

这些流程没有打开真人摄像头。实际 SDK 推理用的是空白帧或合成录像，界面测试使用明确的测试数据；结果不能说明真人测角、计数、动作质量识别或临床效果已经通过验收。

## 本地备份与复现

根目录 `backups/incoming/health-care-software-main-2026-09-10.zip` 保留原始整包，移动后再次核对 SHA256。`backups/integration-20260910/` 包含整理前 Git bundle、源码快照、本机数据备份和同学历史 bundle；详见本地 `backups/README.md`。这些内容不上传 GitHub。

GitHub 只同步源码、必要界面资源、整理文档和可复核摘要。当前电脑可直接使用根目录启动入口；另一台电脑按[开发说明](../DEVELOPMENT.md)重建各自环境。

## 未完成目标

见[当前交接清单](../HANDOFF.md)。压缩包不含同学持续任务的运行状态；长期产品目标、素材、精细方向和双摄方案不能仅因代码已提交而标为完成。
