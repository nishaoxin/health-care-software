# 未来扩展（不属于本周v2.1验收）

当前一台内置/USB摄像头只轮换四场景。以下都不在主依赖、不在启动检查，不设置未连接设备的假在线状态。

## A. 多路视频
只有用户明确新增多路需求后：增加RTSP源、每路独立tracker/state、独立心跳和有效覆盖、调度不饥饿。同一持久化tracker不能交错处理不同房间帧。此时“切康复不得停止其他实际安全流”才成为并行架构要求。跨摄像头ID不是同一居民身份。

## B. 雷达
沿用官方C1001与ESP32驱动思路，但接入时先固定当前驱动版本、检查读取有效性：返回false/0不能单独证明通信成功。保留transport_ok、sensor_ok、字段valid及null，使ESP32在线但雷达失联可以被区分。
首选实测串口后再考虑局域网；pySerial按需安装。真实传感器、回放和人工测试事件严格区分。裸开发模块不是已满足潮湿环境安装的整机。

```text
https://wiki.dfrobot.com/sen0623/docs/21571
https://github.com/DFRobot/DFRobot_HumanDetection
https://pyserial.readthedocs.io/en/latest/shortintro.html
```

## C. 其他
更多动作、精细足部模型、远程家属通知、正式机构权限、医学用途和临床验证分别立项。没有真实接通远程通道就不声称已通知家属或急救。

## D. 研究模型与数据

见`RESOURCES_AND_UPGRADES.md`。当前只补契约、可复现记录和验收；不安装研究网络、训练新模型或批量下载数据。以出错层决定后续投入。
