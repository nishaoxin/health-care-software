# 0.16.0 银发增量｜本机验收记录

日期：2026-09-12；本机 Windows，Python 3.13.12，应用主 `.venv`。基线 `f52ae5b27d4864b4765b5580a3469658a1c8b3a1`。本页不引用旧版本测试数量作为当前结果，也不把合成数据称为真人验收。

## 本轮修改

按用户增量文件完成活动任务决策及检查点、个人许可 / 时长、固定参考变化卡、本机共享 / 家庭回应 / 整改、适老入口及隔离手机测试页面。原康复双摄、准备门禁与模型保留；另一个场景选择 A/B 后依次使用。完整范围、来源和使用步骤见[0.16 说明](../history/SILVER_HEALTH_V0_16.md)。

所有新测试、截图与浏览器使用临时库或明确隔离测试库；未打开真实相机、患者档案或录制现场视频。原临床库无新迁移。稳定 Git 基线另保存为忽略目录中的 `backups/silver-v016/baseline-f52ae5b.bundle`；不是本轮新建的患者数据库备份。

## 完整软件回归

在应用目录运行：

```powershell
.venv/Scripts/python.exe scripts/check_project.py --suite all --timeout 240 --output .runtime/checks/silver-v016-release
```

2026-09-12 00:16:44 UTC 完成，11 批、72 个测试文件全部成功，没有失败、错误、跳过或超时：

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
| 合计 | **1450 项主测试 + 4 项子测试** |

最终又补了“求助保存后自动显示待回应记录”的交互断言，并重跑完整 ui 分区；证据保存在 `.runtime/checks/silver-v016-release-ui`，不与全套数量重复相加。

新增覆盖包括：

- 幂等求助、重复回应、并发版本冲突、实际写入失败不报成功、支持库关闭重开。
- 授权范围、撤销、不同用户 / 来源隔离、旧事件不猜测归属、共享视图不暴露原始证据。
- 查看、认领、处理分开；整改必须本人确认；事件不会仅因查看或连接状态变更自动结束。
- 3～5 次固定参考、当前与参考不重叠、缺条件 / 换机位 / 换目标 / 低质量拒绝比较、原报告指纹改变作废。
- 提醒、拒绝后不重新催促、活动许可限制、缺测中断、自报不等于视觉核实、未接受提醒不能自报为完成。
- 求助不依赖相机或待完成刷新；连续 B 场景切换回康复恢复 A/B；可选模块报错不改实时康复指导。
- 慢可选任务使用冻结快照和独立队列：派发快速返回，活控制器不跨线程使用，任务失败不改变采集状态。
- 真 HTTP 短时配对 / 电脑确认、过期 / 次数限制、Host / Origin / CSRF、授权撤销、事务失败响应、回执落库与重复请求。

测试中的失效注入不代表实际拔线、磁盘损坏、家庭网络故障或所有并发情况都完成现场验收。

## 原生页面与浏览器

`scripts/qa_silver.py` 使用 offscreen Qt、真实新服务适配器和临时数据库，生成并检查四个页签在 1040×760 / 800×600 下的截图、本机家属角色与手机控制窗口。结果在 `.runtime/qa-silver-v016/`。小窗口允许纵向滚动，未使用真实用户数据、音频或网络。

浏览器控制工具两次初始化均报本机资源路径缺失，未继续反复等待。改用随工作区提供的 Playwright 与系统 Edge 无头模式；没有安装新浏览器包、修改系统权限或使用用户浏览器档案。

```powershell
$env:NODE_PATH='C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
& 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' scripts/qa_family_page.cjs
```

浏览器使用 390×844 视口和 **127.0.0.1 回环地址**。独立 Python 夹具持有临时隔离库、限时关闭服务。实际通过：网页输入一次性码 → 等待电脑批准 → 读取 TEST_EVENT → 点“我已查看” → “我来联系 / 处理” → 填处理说明 → 页面显示已处理。最终数据库状态 RESOLVED，历史顺序 ack / claim / resolve，通道均为 LAN_FOREGROUND_TEST_ONLY；零 pageerror，无横向溢出。截图 `phone-pair.png`、`phone-request.png`、`phone-resolved.png` 与 `browser-result.json` 留在忽略的运行目录中。

这里验证的是浏览器与服务器真实交互，**没有验证实体手机、实际局域网、锁屏 / 后台通知或真实家属响应**。启用声音按钮存在，但未自动播放或把无头浏览器结果当作可听度验证。

## 检查中修复的问题

- 首次原生截图发现控件名 `metric` 覆盖 Qt 同名方法，已改为 `metric_select` 并重新跑截图与回归。
- 连续进入 B 的不同场景可能覆盖 A 的返回选择，已保留原 A 并加入多场景恢复测试。
- 可选库操作可能等待数秒从而拖住采集调度，已改为独立有界队列；任务只收到冻结结构化快照，不收到真实摄像头 / 控制器。
- 拒绝记录、提醒接受和完成的状态历史补齐；待接受提醒不能“自报完成”。
- 求助成功原先只更新隐藏列表，现自动定位到已保存请求，明确展示待回应。

## 未完成的现场验收与后续

真人动作精度 / 重复性、真实双摄长时间与断流释放、未参与开发的老人独立操作、实际手机前台回执、真实声音可听度均未在本轮验证。正式远程 HTTPS / 认证 / 患者资料共享 / 后台推送没有实现。通用日程、跨天静默、家属代报、环境照片、选做健康事项和新示范素材未交付。原临床定义与已标记的精细动作限制不变。

## Git 交付

本轮按项目约定提交并尝试推送；最终本地提交号、推送返回与远端一致性核对以交付消息及实际 Git 输出为准。未成功认证 / 推送时，不把本地提交描述为已上传。
