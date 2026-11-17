<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_media_kit?name=astrbot_plugin_media_kit&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# 媒体解析工具箱

_✨ 自动解析流媒体平台链接，先发信息卡片，再聚合发送媒体直链 ✨_

[![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![Version](https://img.shields.io/badge/Version-v1.3.0-green.svg)](https://github.com/Eason4869/astrbot_plugin_media_kit)

</div>

---

媒体解析工具箱是一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件：群里发送主流视频 / 图文 / 游戏平台链接时，机器人自动解析，**先发送一张精美的信息卡片**（标题、作者、封面、统计数据），**再把视频和图片聚合发送**。开箱即用，无需配置即可解析大部分平台。

## ✨ 特性

- 🎴 **rika 风格卡片渲染**：把标题、作者、头像、封面、播放/点赞等统计渲染成图片卡片，支持 `标准` / `杂志` / `沉浸式` / `信息流` 四种布局与深 / 浅主题；封面下载失败自动兜底
- 🤖 **群聊贴表情仲裁**：群里有多个机器人时，通过贴表情自动竞争解析权，保证一条链接只有一个机器人响应；同时用贴表情反馈解析状态（占坑 / 成功 / 失败）
- 📺 **多平台聚合解析**：B站、B站直播、抖音、TikTok、快手、微博、小红书、闲鱼、今日头条、小黑盒、Steam、Twitter/X、Pixiv
- 🔁 **灵活发送**：消息聚合（不聚合 / 全部聚合 / 按条件聚合）、媒体中转、引用链接一键导出 ZIP
- 📝 **正文翻译**：可选大模型翻译标题与正文（AstrBot 内置 AI 或自定义 OpenAI 兼容接口）
- 🛠️ **细粒度配置**：每个平台可独立设置全部发送 / 仅文本 / 仅富媒体 / 关闭，支持解析频率限制、白黑名单、分平台代理、B站 Cookie 高画质与扫码协助登录
- ⌨️ **常用管理命令**：强制解析（绕过频率限制）、解析状态、清理缓存、引用 ZIP 归档；可选限流提示与多链接进度

---

## 📺 支持平台

<table>
<thead>
<tr>
<th>平台</th>
<th>支持的链接类型</th>
<th>能力</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>B站</strong></td>
<td>短链（<code>b23.tv/...</code>）、视频（<code>bilibili.com/video/av|BV...</code>）、番剧（<code>bangumi/play/ep|ss...</code>）、动态（<code>opus/...</code>、<code>t.bilibili.com/...</code>）、小程序卡片</td>
<td>视频 / 图片 / 文本 / 热评</td>
</tr>
<tr>
<td><strong>B站直播</strong></td>
<td>直播间链接（<code>live.bilibili.com/&lt;房间号&gt;</code>）</td>
<td>仅卡片（含直播间封面，不下发媒体）</td>
</tr>
<tr>
<td><strong>抖音</strong></td>
<td>短链（<code>v.douyin.com/...</code>）、视频（<code>douyin.com/video/...</code>）、图集 / 多分段（<code>note/</code>、<code>slides/</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>TikTok</strong></td>
<td>短链（<code>vm.tiktok.com/...</code>、<code>vt.tiktok.com/...</code>）、视频（<code>@user/video/...</code>）、图集（<code>@user/photo/...</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>快手</strong></td>
<td>短链（<code>v.kuaishou.com/...</code>）、作品（<code>kuaishou.com/...</code>、<code>gifshow.com/...</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>微博</strong></td>
<td>微博视频 / 图文链接</td>
<td>视频 / 图片 / 文本 / 热评</td>
</tr>
<tr>
<td><strong>小红书</strong></td>
<td>笔记链接（<code>xiaohongshu.com/explore/...</code>、<code>xhslink.com/...</code>）；移动端分享链接自动去水印</td>
<td>视频 / 图片 / 文本 / 热评</td>
</tr>
<tr>
<td><strong>闲鱼</strong></td>
<td>商品链接（<code>goofish.com/item?id=...</code>、<code>h5.m.goofish.com/item...</code>，短链 <code>m.tb.cn/...</code> 自动跟随跳转）</td>
<td>图片 / 文本</td>
</tr>
<tr>
<td><strong>今日头条</strong></td>
<td>短链（<code>m.toutiao.com/is/...</code>）、文章 / 视频 / 微头条（<code>toutiao.com/article|video|w/...</code>）、小程序卡片</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>小黑盒</strong></td>
<td>游戏详情（<code>xiaoheihe.cn/app/topic/game/...</code>、<code>api.xiaoheihe.cn/game/share_game_detail?...</code>）、BBS 帖子（<code>app/bbs/link/...</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>Steam</strong></td>
<td>商店游戏页（<code>store.steampowered.com/app/...</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>Twitter / X</strong></td>
<td>推文链接（<code>twitter.com/.../status/...</code>、<code>x.com/.../status/...</code>）</td>
<td>视频 / 图片 / 文本</td>
</tr>
<tr>
<td><strong>Pixiv</strong></td>
<td>插画 / 漫画（<code>pixiv.net/artworks/...</code>、<code>pixiv.net/i/...</code>，支持 <code>/en/</code> 前缀）</td>
<td>图片 / 文本</td>
</tr>
</tbody>
</table>

---

## 🚀 安装

1. 依赖会在插件安装时依据 `requirements.txt` 自动安装：`aiohttp`、`cryptography`、`qrcode[pil]`、`pillow`
2. 在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_media_kit` 安装，或把本仓库克隆到 AstrBot 的 `data/plugins/` 目录后重启

安装后无需任何配置即可解析大部分平台。

---

## 🧩 解析器与输出模式

### GitHub 与京东：默认卡片，按需详细解析

- **GitHub**：支持公开仓库、Issue、PR、Release（含最新发布链接）。普通链接展示项目统计或标题、作者和状态；引用原链接消息并发送 `详细解析`，返回 README、Issue 正文及最多 10 条最新讨论、PR 正文及最多 20 个文件的差异片段，或版本说明与最多 20 个附件链接。不会自动克隆仓库、下载发布附件。
- **GitHub Token 可选，可以留空**：匿名也能解析公开资源，但 API 额度较低（通常每个出口 IP 每小时 60 次），插件缓存数据 5 分钟并使用条件请求。即使配置的 Token 有私有权限，插件也只处理公开资源。
- **GitHub 内置代理选项**：在 `代理设置 → GitHub 代理` 分别控制 `解析` 与 `图片下载`，复用现有 `代理地址`，使用方式与 Twitter/X 一致，均不依赖 Token。默认解析代理关闭、图片代理开启；未填写代理地址时仍直连。
- **可选 AI 摘要**：只在 GitHub 详细解析时调用，默认使用当前会话的 AstrBot 模型；可在 GitHub 设置指定模型，也可复用文本翻译中的自定义模型连接配置，**无需开启翻译**。先发送原始详情，再补发明确标注的中文 AI 摘要。输入最多 24,000 字符、输出最多 1,000 字符、总等待最多 30 秒；按内容与模型缓存 30 分钟。模型不可用时保留原始详情，摘要不等同于完整代码审计。
- **GitHub 图片**：详细解析提取正文中最多 6 张图片，过滤常见徽章／统计图片，支持 README 相对图片路径；不会递归访问正文中的外部网页。
- **京东**：商品卡片包含品名、缩略图、可获取的店铺与参考价格；普通链接不发送商品图集。引用后发送 `详细解析`，按主图、详情图顺序去重发送，单商品最多 20 张，沿用媒体下载限制和消息聚合配置。价格取不到时显示“暂未获取”，不会用推荐商品价格补齐。
- **京东可用范围**：已真实验证 `item.jd.com/product/<标识>.html` 新版页面。数字商品链接、移动链接与 `u.jd.com` / `3.cn` 短链具备识别和展开路径，但站点可能返回登录或风控页面；HTTP 无法取得商品数据时可用临时访客浏览器回退（含排队最多 30 秒），仍可能受限，不保证全部链接可用。可在京东设置关闭回退或指定浏览器路径。
- **淘宝暂未启用**：本次匿名页面与接口未通过真实商品卡片及多图验证，因此不提供未验证的开关，也不改变闲鱼的 `m.tb.cn` 短链路由。

`详细解析` 沿用普通解析权限，可在 `管理与调试` 修改或置空关闭。普通与详细请求分别计算同链接限流，共享用户限流；该命令不绕过限流。仍遵守平台输出模式：`仅文本` 不发详情图片，`仅富媒体` 不发原文或 AI 摘要；只有富媒体输出时，普通链接会提示按需详细解析。归档提取原始详情但不自动调用 AI。

在 `解析器与输出模式` 中，每个平台可独立选择：

- `关闭`：不解析该平台链接
- `全部发送`：发送卡片 / 文本元数据，并发送图片、视频
- `仅文本`：只发送卡片 / 文本，不下载发送媒体
- `仅富媒体`：只发送图片、视频

默认所有平台均为 `全部发送`。

> **B站直播**平台仅提供 `关闭 / 全部发送 / 仅文本` 三种模式（直播本就只产生卡片，不发媒体）；建议保持 `全部发送`。

---

## 🎴 卡片渲染

在 `消息输出 → 附加内容：卡片渲染` 中开启（依赖 pillow）。可配置：

- **布局**：标准（顶部全宽封面）/ 杂志（左封面右信息）/ 沉浸式（全幅背景）/ 信息流（紧凑列表）
- **主题**：深色 / 浅色
- **模式**：卡片 + 文本同条发送、卡片 + 文本分别发送、仅卡片
- 卡片宽度、封面是否全幅展示、视频封面是否显示播放按钮、自定义字体

渲染失败会自动回退为纯文本，不影响媒体发送。修改视觉样式后旧卡片缓存会自动失效并重渲染。

> 发送顺序固定为：**先发送信息卡片，再聚合发送视频与图片**。

---

## 🤖 群聊贴表情仲裁与状态反馈

在 aiocqhttp（OneBot v11，如 NapCat、Lagrange）平台的**群聊**中，机器人会在被解析的链接消息上贴 QQ 表情：

- **多 Bot 仲裁**：同一条链接被群内多个支持该协议的机器人同时看到时，机器人之间通过固定表情（占坑、胜出确认）的点赞列表做弱一致仲裁，最终只有一个机器人解析并发送，避免重复刷屏。仲裁顺序按消息时间片确定性轮转，所有机器人结论一致；该协议与 [astrbot_plugin_parser](https://github.com/Zhalslar/astrbot_plugin_parser) 兼容，不同插件的机器人同群也能互相仲裁。
- **状态反馈**：识别到链接即贴占坑表情（已接手），解析成功贴成功表情，解析失败贴失败表情，方便判断机器人是否在运行。

默认开启，仅在协议端支持 `set_msg_emoji_like` / `fetch_emoji_like` 的群聊中自动生效；私聊、其他平台或不支持的协议端自动跳过，不影响解析。

可在 `贴表情反馈与多 Bot 仲裁` 配置项中分别控制：

- `启用多 Bot 贴表情仲裁`：关闭后本插件不再参与贴表情仲裁（只靠协议端/其他仲裁逻辑避免重复解析）。占用表情 289/124 是跨插件协议的一部分，**不可修改**，否则会与 astrbot_plugin_parser 的机器人失配。
- `启用成功/失败状态贴图`：控制解析成功/失败时是否贴状态表情。
- `成功表情 ID` / `失败表情 ID`：可自定义成你的协议端贴表情面板中存在且语义合适的表情 ID（默认“对的对的”=478、“不对不对”=479）。若协议端不支持某个表情，会被静默忽略、不影响解析。

---

## 🎮 Steam 与小黑盒

- **Steam**：`store.steampowered.com/app/<appid>/...` 默认调用 Steam 官方 `appdetails` 接口获取游戏信息、截图与预告视频。在 `Steam 设置` 中开启「使用小黑盒路径」后，改用小黑盒完整游戏详情，可获得小黑盒评分、在线人数等更多统计。
- **小黑盒**：游戏详情走签名接口（含评分、价格、类型、发行信息、预告视频），BBS 帖子解析正文与媒体。相关加解密依赖 `cryptography` 库。

Steam / 小黑盒媒体多走 Steam CDN，下载速度不佳时可在 `代理设置 → Steam 代理` 中为解析 / 图片 / 视频分别启用代理。

---

## 🔴 B站直播（仅卡片）

发送 `live.bilibili.com/<房间号>` 直播间链接时，机器人**只返回一张信息卡片**：以直播间封面为卡片主视觉，展示直播间标题、作者、开播状态、在线人数、分区与公告。**不下载、不发送任何视频或图片媒体**，避免对持续直播流的无意义下载。

- 使用 B站公开房间接口（`room/v1/Room/get_info`）与直播间页面获取信息，无需登录
- 支持 `b23.tv/...` 直播短链：解析器会先展开短链，确认为直播间后解析；若短链指向视频等内容则自动交由对应平台解析器处理
- 未开播的房间同样返回卡片，并标注「未开播」
- 直播间封面缺失或图片下载失败时卡片自动回退为纯文本，不影响文字信息展示
- 该能力通过独立的 **「B站直播」** 平台开关控制（`解析器与输出模式` → `B站直播`）
- 作为**仅卡片结果**返回时，不会误提示「没有可发送的内容 / 下载失败」——卡片本身即解析结果
- 抖音直播因页面不携带房间数据、接口风控强，暂不支持解析

---

## 📦 消息聚合、封面与 ZIP 归档

- **聚合模式**（`消息输出 → 发送行为：消息聚合`）：`不聚合` 逐条发送；`全部聚合` 尽量用合并转发（超过大视频阈值的媒体仍单独发送）；`按条件聚合` 在图片 / 视频 / 节点数达到阈值时聚合。
- **视频仅发送封面**：开启后不发视频，改为发送封面图；无封面时尝试用 ffmpeg 截取第一帧（依赖缓存目录与 ffmpeg）。
- **ZIP 归档**：在 `导出行为：ZIP 归档` 配置命令后，引用含链接的消息并单独发送该命令，即可把解析详情与已下载媒体打包为 ZIP（含 `metadata.txt` 与 `details.json`），媒体总量受上限约束。

**解析频率限制** 默认关闭，可分别按「同链接」「同用户」设置时间窗内最大解析次数，记录持久化并自动裁剪。

---

## 🍪 B站 Cookie 与画质增强

配置 Cookie 后可解锁更高画质（1080P+、4K），视频通过 DASH 音视频流下载合并（需缓存目录可用）。

- 在 `B站增强 → 携带 Cookie 解析` 开启并填入 Cookie（浏览器 F12 → Network → 任意请求的 Cookie 头），选择最高画质。
- **管理员协助登录**：开启后 Cookie 失效时机器人私聊管理员引导扫码续期；管理员也可私聊发送 `B站更新Cookie` 立即发起扫码。
- 缓存目录不可用时会自动旁路 Cookie / DASH / 协助登录，回退无 Cookie 直链。

---

## 🖼️ Pixiv

支持插画与漫画多页图片，优先原图，附带作品标签并标注 R-18 / R-18G / AI 生成状态。登录或年龄限制作品需在 `Pixiv 设置` 填写含 `PHPSESSID` 的 Cookie；无法直连时配置代理地址并开启 Pixiv 代理。Pixiv 图片需带 Referer 下载并缓存发送。

---

## 🔁 媒体中转模式

当 AstrBot 与协议端（NapCat、Lagrange 等）**不在同一台机器**或**无法共享文件目录**时，本地下载的媒体对协议端不可达。开启 `媒体中转` 后，通过 AstrBot 内置 HTTP 服务把已缓存文件转为临时回调 URL 发送：填写协议端可达的 AstrBot 回调地址（如 `http://host:6185`）并设置缓存有效期即可。该模式只增强已成功缓存的媒体，不强制下载全部媒体。

---

## ⚙️ 缓存目录与网络建议

确保**媒体缓存目录可用**能显著提升成功率：消息平台用直链发送媒体时无法带 header / referer / cookie，风控严格的平台会返回 403。

- **必须缓存目录**：图片发送、B站 DASH 合并、微博视频（需 referer）、小黑盒视频 / M3U8、Twitter/X 视频、Pixiv 图片。
- **建议缓存目录**：TikTok、小红书（媒体有时效与鉴权）。
- Docker 部署请把缓存目录配置为协议端可访问的共享目录；非 Docker 环境自动使用 AstrBot 插件数据目录。
- TikTok / Twitter / Pixiv 等受地区与风控影响明显，必要时在 `代理设置` 配置代理。媒体连接只允许公网地址，显式配置的代理视为受信端点；Clash/TUN 的 `fake-ip` 模式可能把域名映射到保留网段被安全策略拒绝，请改用 `redir-host` / 真实 DNS。

### 抖音浏览器回退

HTTP 解析遇到风控或无法取得作品数据时，默认使用本机 **Chromium / Chrome / Edge** 打开作品页并读取页面自身的详情响应。每次使用独立临时访客目录，不读取已有浏览器账号，不需要登录；同时最多运行一个回退会话，解析等待最多 30 秒，完成或取消后关闭浏览器。站点仍可能要求人工验证，该场景会返回明确的超时提示，不保证所有账号、网络和作品都能解析。

- Windows 自动查找已安装的 Chrome / Edge；macOS 查找标准应用路径；Linux 查找 PATH 内的 Chromium / Chrome / Edge。
- Linux / Docker 需在 **AstrBot 所在环境**安装 Chromium，浏览器必须能在当前用户下正常启动并使用沙箱。推荐以普通用户运行；插件不会自动关闭浏览器沙箱。
- 可在 `抖音设置` 指定浏览器可执行文件路径，或关闭浏览器回退。没有浏览器时，正常 HTTP 解析仍可使用；只有需要回退时才提示安装。
- 浏览器使用部署环境的正常网络，详情数据取得后，视频仍走插件现有下载流程。视频地址有时效，建议使用可用的媒体缓存目录。

---

## ⌨️ 常用命令

| 命令 | 谁可用 | 作用 |
|------|--------|------|
| （发送链接，自动） | 权限内用户 | 自动解析并发送卡片与媒体 |
| 引用消息 + `强制解析` | 管理员（默认） | 绕过解析频率限制再解析 |
| 引用消息 + 归档命令 | 权限内用户 | 将解析详情与媒体打包为 ZIP |
| 私聊 `清理媒体` | 管理员 | 清理媒体缓存 |
| 私聊 `解析状态` | 管理员 | 查看版本 / 平台 / 缓存 / 限流概况 |

以上关键词均可在 `管理与调试` / `导出行为：ZIP 归档` 中修改；置空对应关键词可关闭该命令。命令关键词两两不能相同，冲突时会保留高优先级命令并写日志警告。

**解析频率限制**默认关闭。启用后，同链接 / 同用户在时间窗内超出次数会被静默拦截；可开启「被限流时提示」，并配合「强制解析」让管理员显式重解析。

---

## 📝 其他说明

- 机器人自动跳过自身消息以防重复解析。
- **B站直播**：`live.bilibili.com/&lt;房间号&gt;` 链接返回仅信息卡片（标题、作者、直播间封面、开播状态、分区、公告），不下发视频 / 图片媒体；依赖 B站公开接口，无主播封面或接口风控时卡片可能缺失封面但仍发送文字。抖音直播因公开页面不携带房间数据、接口强风控，暂不支持解析。
- 非 JPG/PNG 图片会尝试转换为 PNG，转换失败保留原格式；HLS 选择最高分辨率并用 ffmpeg 封装，拒绝 `EXT-X-BYTERANGE` 清单以避免损坏文件。
- 触发方式：默认自动解析消息中的链接；也可配置手动触发关键词，或引用含链接的消息并附关键词触发。

---

## 🙏 鸣谢

- [astrbot_plugin_media_parser](https://github.com/drdon1234/astrbot_plugin_media_parser) — 解析器与下载器基础
- [astrbot_plugin_rika_share](https://github.com/iris1598/astrbot_plugin_rika_share) — 卡片渲染器（MIT License），底层基于 [nonebot-plugin-parser](https://github.com/maoxig/nonebot-plugin-parser) 的 CommonRenderer
- [astrbot_plugin_parser](https://github.com/Zhalslar/astrbot_plugin_parser) — 贴表情仲裁协议
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) — B站解析端点
- [FxEmbed](https://github.com/FxEmbed/FxEmbed) — Twitter/X 解析服务
- [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) — 抖音签名实现（移植部分遵循 Apache-2.0，见 `LICENSES/Apache-2.0.txt`）

欢迎提交 Issue 与 PR。
