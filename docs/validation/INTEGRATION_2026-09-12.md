# 2026-09-12 新压缩包整合与本机验收

应用版本 **0.16.0**。本次将同学的新版本整理接入当前工程，保留原运行环境、模型和个人数据；应用源码直接继承已核对的提交，没有另改业务逻辑或数据库结构。

## 来源与版本关系

- 用户提供 `health-care-software-main.7z`，401780203 字节。
- SHA256：`5da5441880b13a409cc3e79a195b00409b471da40ed9e4268cb9795c8e7808df`；移入备份后再次校验一致。
- 整理前本地与 GitHub `main`：`f7c69bb2dfc4bc6b346561f1fb298144975c0789`，应用 0.14.0；没有未提交源码改动。
- 包内 `main`：`dea7aa13cce9882f703c1058792e8c46658f59ca`，应用 0.16.0；工作区与提交一致，没有未提交文件或未解决的合并冲突。
- 包内 Git 对象完整性检查通过，无缺失或损坏对象；一个未引用的 dangling tree 不属于未提交源码。通过经过验证的 bundle 导入，再执行 `merge --ff-only`，没有复制其 `.git` 到当前仓库。

| 新增提交 | 内容 |
| --- | --- |
| `199a265` | 同学分支的逐步准备、取景解释和结果解读 |
| `f52ae5b` | 将上述分支与本机原 `f7c69bb` 双父合并为 0.15.0 |
| `dea7aa1` | 0.16.0 活动闭环、固定参考变化卡、本机家庭回应 / 整改及隔离手机演示 |

相对原版本共 44 个文件发生变更，3 个新增提交和双方已有历史完整保留。9 月 10 日导入的 12 个提交已在旧历史中，不重复计入本次。逐项文件与归档盘点见[导入清单](results/2026-09-12-import.json)。

## 文件夹整理

根目录只保留启动入口、环境准备、项目说明、应用目录、`docs/` 和本地 `backups/`。应用仍在 `rehab_codex_single_camera_v2_1/`，兼容原启动脚本、独立环境和数据位置。

本次备份集中在 `backups/incoming/2026-09-12/`：

| 文件 / 目录 | 用途 |
| --- | --- |
| `health-care-software-main.7z`、`SHA256.txt` | 原始整包及校验值 |
| `before-integration.bundle` | 本机整理前的全部 Git 引用与历史 |
| `classmate-history.bundle` | 完整、已验证的同学主分支历史 |
| `local-data-before/` | 整理前本机数据副本 |
| `extracted/health-care-software-main/` | 筛除环境、模型二进制、数据和缓存后的隔离核对目录 |
| `archive-entries.txt` | 原包条目清单 |

原包共有 40936 个条目，其中两套虚拟环境有 39111 个条目；这些环境、包内个人数据库、运行日志和 QA 数据均未合入当前工作目录。原本机所有数据文件与备份逐文件比较，内容哈希一致。早期备份继续保留，未删除。

文档继续集中在 `docs/`：使用 / 交接 / 开发为入口，版本历史在 `history/`，验收在 `validation/`。本次更新交接中的提交关系、当前版本和备份位置；同学的三份原验收加上来源标记，保留原计数和失败经过。首页截图更新为本机 0.16.0 独立空库启动。`.gitignore` 新增根目录 `/*.7z`，保留全部原忽略规则。

## 当前电脑重新执行的验证

Windows x64，原主环境 Python **3.13.11**；主环境与可选关键点环境分别执行 `pip check`，均无依赖冲突。没有安装依赖、下载模型或混用同学的 Python 3.13.12 环境。

完整回归命令，在应用目录执行：

```powershell
.venv/Scripts/python.exe scripts/check_project.py --output .runtime/checks/integration-20260912-first
```

2026-09-12 04:35:36 UTC 完成。72 个测试文件分为 11 个互不重复批次，**1450 项主测试及 4 项子测试通过，0 失败、0 错误、0 跳过、0 超时**。首轮完整执行即通过；随后只有文档、截图及忽略配置整理，应用源码没有进一步修改。批次耗时合计 107.09 秒。

| 批次 | 主测试通过数 |
| --- | ---: |
| core | 837，另 4 项子测试 |
| ui | 392 |
| joint expansion flow | 21 |
| optional landmarks | 179 |
| runtime integration | 3 |
| source integration | 1 |
| vision integration | 2 |
| camera test integration | 3 |
| dual runtime integration | 5 |
| dual vision integration | 1 |
| model paths integration | 6 |

[本机完整结果](results/2026-09-12-final.json)包含各批文件、耗时、JUnit 计数和 pytest 原文。JUnit 的 1454 已包含 4 项子测试，不额外再加。原始日志和 XML 保留在本地上述 `.runtime/checks/` 目录。

### 桌面、浏览器和保存路径

以下全部使用临时库或明确标记的 SYNTHETIC / TEST 数据：

- `qa_journey.py`：14 张原生截图；1100×730 / 1360×900 的取景、起点、倒计时、方向、最终确认和保存失败，以及 1020×680 的报告解读；结果在 `.runtime/qa-journey-v015/`。
- `qa_silver.py`：10 张原生截图；1040×760 / 800×600 的四个页签、本机家属角色和手机控制窗口；结果在 `.runtime/qa-silver-v016/`。小窗口内容通过纵向滚动查看，顶部求助 / 暂停与底部返回入口保留。
- `qa_quiet_guidance.py --output qa-output/integration-20260912-quiet`：14 张截图及 SQLite 关闭重开、HTML / JSON / CSV 导出；覆盖准备、短暂 / 持续缺测、恢复、双摄辅助缺测、大字指导和保存失败恢复。
- `qa_family_page.cjs`：使用本机已有 Playwright 与 Edge 无头浏览器，在 127.0.0.1 和 390×844 视口完成一次性码 → 等待电脑批准 → 查看 → 认领 → 记录处理结果。回执落库为 RESOLVED，历史为 ack / claim / resolve，通道为 LAN_FOREGROUND_TEST_ONLY；零页面错误、无横向溢出。3 张手机页面截图及 `browser-result.json` 在 `.runtime/qa-silver-v016/`。
- 真实 `app.main` 入口：指定 `qa-output/integration-20260912-startup/data` 独立目录，offscreen 启动、截图后正常退出；没有打开摄像头。[首页截图](../images/home.png)没有个人资料或相机画面。

已目视检查本机生成的小窗口四页签、倒计时、结果解读、保存恢复、大字调整和手机处理结果。全部测试没有开启真人摄像头、播放声音或向真实家属发送消息。

`compileall -q app scripts tests`、PowerShell 启动 / 准备脚本语法解析、相对 Markdown 链接和 `git diff --check` 均通过。现有启动入口可继续使用，无需重新安装环境。

## 当前范围与后续

本次完成整包接入和当前电脑的软件复核。包内关于“双摄可用”的用户反馈保留为来源记载，没有用它替代独立的设备、真人精度或长期稳定性验收。实际手机、真实局域网、锁屏通知和语音可听度也未在本次验证。

原增量建议 `E:/SILVER_HEALTH_INCREMENTAL_PLAN.md` 未包含在 7z 中；当前已交付内容与未完成项以代码、[0.16 功能说明](../history/SILVER_HEALTH_V0_16.md)及[当前交接](../HANDOFF.md)为据。本次没有推定需要补做新的远程产品功能。

GitHub 同步源码、必要界面资源、整理文档和可复核摘要；整包、虚拟环境、模型权重、个人数据和本地运行日志继续只保留在本机。
