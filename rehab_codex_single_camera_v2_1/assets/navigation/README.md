# 人体部位导航图

- 文件：`body-front-v1.png`，1024 × 1536，RGBA PNG。
- 来源：2026-09-09 使用 Codex 内置 ImageGen 生成；未下载第三方人物照片。生成模式为新图生成，无参考图、无 API/CLI 回退。
- SHA-256：`b22c59f31ede1b18f62533c0814d8e704c8614237278d109a675f26f81ba2e78`。
- 用途：身体部位菜单的背景。图标、名称和连接线由 Qt 提供真实交互；不是动作指导图片、临床解剖图、校准参照或关键点模型，不参与测量。
- 没有生成患者动作示范图。原有 `exercise-guides` 的缺图文字和素材审核要求保持不变。
- 文件已复制进项目，运行不依赖生成缓存或联网。资产缺失时仍可点击部位文字。

## 最终生成提示词

```text
Use case: stylized-concept. Asset type: a single human body illustration for a rehabilitation desktop application's interactive body-part navigation, not a medical/anatomical measurement or exercise demonstration. Produce a 1024x1536 portrait PNG with genuinely transparent background. Center one full-body front-facing adult, gender-neutral, simple friendly featureless face, natural realistic proportions, standing upright neutrally, legs comfortably slightly apart, arms gently angled down and away from torso (about 18 degrees) so shoulders, elbows, wrists, palms and fingers are separated from the torso and visibly locatable. Both arms straight but relaxed. Bare feet visible, hands open relaxed with all five fingers per hand, no extra limbs or fingers. Modest plain short-sleeve light-lavender top and darker muted lavender knee-length shorts. Soft premium flat vector-like illustration with very light dimensional shading, fine clean edges, calm healthcare/sports-app style, purple-gray palette matching #7048df accent, no muscle or skeleton details. The full person should occupy x approximately 25%-75% of image width and y approximately 5%-95% of image height, centered straight-on and symmetrical. Keep entire head, hands and feet within frame. No text, no labels, no icons, no circles, no arrows, no background scene, no floor, no watermark. The application will overlay interactive labels and joint markers separately.
```
