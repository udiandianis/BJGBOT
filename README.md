# BJGBOT

通过 NapCat OneBot11 接收 QQ 群消息的 Python 机器人，用户绑定、积分、分配题目和单挑状态保存在 SQLite。

## 启动与配置

Windows 双击 `scripts/start.bat`，Linux 运行 `bash scripts/start.sh`。脚本会创建对应的虚拟环境并安装统一的 `requirements.txt` 依赖。Windows 也可运行 `scripts/start.bat --prepare-only` 单独准备依赖。

首次部署时，将 `config/bot_settings.example.json` 复制为同目录下的 `bot_settings.json`，填写机器人 QQ 号、R2 连接信息及实际 NapCat 路径。需要管理收藏时填写 `collections.admins`；使用 AI 时填写对应服务地址、模型和密钥，使用洛谷查询时填写 Cookie。示例中的 `0` 和空值需要按实际用途填写，示例文件不参与运行，真实配置已被 Git 忽略。

Windows 还需先安装 Python 3.10 或更高版本和 NapCat；Linux 脚本可在 Ubuntu/Debian 自动准备 Python、系统工具、NapCat 和匹配的 Linux QQ。启动脚本自动安装机器人 Python 依赖，启动 NapCat 和机器人后端；服务已运行时跳过重复启动。

唯一运行配置是 `config/bot_settings.json`。启动脚本和后端均要求配置文件存在，缺失时直接报错。`src/settings.py` 只声明字段、读取并校验 JSON，没有配置默认值，也不使用环境变量覆盖 JSON。修改配置后重启后端；NapCat 自身的监听和上报设置还需在其 WebUI 中同步修改。

| 字段 | 含义 |
| --- | --- |
| `bot.qq` | 机器人 QQ 号 |
| `bot.host` / `bot.port` | Python 消息上报接收地址，示例为 `127.0.0.1:5010` |
| `napcat.api_url` / `napcat.api_token` | 调用 NapCat 发送消息等接口的地址和令牌，示例端口为 `5020` |
| `napcat.webui_port` | 启动脚本检测 NapCat WebUI 的端口 |
| `napcat.windows_launcher` | Windows NapCat 启动器的完整路径 |
| `napcat.linux_qq_path` | Linux 已安装 NapCat 的 QQ 可执行文件路径，支持 `~` |
| `bot.request_timeout` | NapCat、平台查询及 AI 建立连接的超时，单位秒 |
| `welcome.groups` / `welcome.message` | 欢迎消息生效的群号及纯文本；程序自动 @ 新成员，无需填写 CQ 码 |
| `collections.admins` | 允许使用删除、清空指令的 QQ 号；首位同时作为社区 Agent 主人 |
| `ai.request_timeout` | AI 回答读取超时，单位秒，建议 120；独立于普通请求 |
| `ai.chatgpt.base_url` / `ai.chatgpt.model` / `ai.chatgpt.api_key` | ChatGPT 服务地址、模型和密钥 |
| `ai.deepseek.base_url` / `ai.deepseek.model` / `ai.deepseek.api_key` | DeepSeek 服务地址、模型和密钥 |
| `platforms.luogu.cookies` | 洛谷查询所用 Cookies |
| `problemset.refresh_time` | 题库每天更新的北京时间，格式为 `HH:MM`，当前为 `00:00` |

`PYTHON_BIN` 仅用于让启动脚本选择 Python 解释器。机器人账号、端口、平台密钥及 NapCat 路径均读取 JSON。本地配置和数据库不应提交到版本库。

数据流：QQ → NapCat HTTP 上报 → `app.py` → 消息解析 → 命令路由 → 业务服务 → NapCat HTTP API → QQ。5010 用于接收事件，5020 用于调用 QQ 操作，两者分别属于 Python 和 NapCat。

## 代码结构

大肥鱼接入、远端部署和社区功能说明见 [社区 Agent 说明](resources/agent/README.md)。原有业务指令仍优先由 BJGBOT 处理。

```text
scripts/                 Windows 和 Linux 启动脚本
config/                  运行配置
resources/
  data/                  SQLite 数据库及题库
  images/                日历背景、勾选图标
  fonts/                 黑体、Noto 字体及许可文件
output/                  签到月历、统计表、下载缓存
src/
  main.py                启动入口
  app.py                 HTTP 接口、异常处理与响应发送
  events.py              统一解析数组消息和 CQ 字符串
  router.py              命令匹配及帮助生成
  settings.py            JSON 配置读取与校验
  commands/              按功能注册命令
  services/              查询、单挑、结算、统计、签到、文件收藏
  providers/             平台接口
  adapters/              NapCat 客户端及 HTTP 请求
  storage/               SQLite 数据读写与 R2 对象存储
tests/                   功能测试
```

平台统计统一使用 `current_rating`、`highest_rating`、`total_submissions`、`accepted_submissions`、`today_submissions`、`today_accepted_submissions` 等名称。`seconds_since_latest_submission` 是距最近提交的秒数；`latest_submission_accepted` 是最近一次提交是否通过；`attempts_for_latest_problem` 和 `accepted_attempts_for_latest_problem` 是最近题目的提交及通过次数。AC 提交次数可能包含重复通过同一道题，不等于通过题目数。

## 指令

`#help` 根据当前命令注册生成，具体用法和权限以它为准。

- `#bind name 姓名`、`#bind class 班级`、`#bind codeforces/nowcoder/luogu/atcoder 账号`、`#bind chaoxing 账号 密码`。
- `#codeforces/nowcoder/luogu/atcoder 账号`：查询指定平台账号；`#平台名 @某人` 或 `@某人 平台名`：查询对方绑定的账号。
- `#近期比赛`：CF 和 AtCoder 比赛；`#GPT 问题`：GPT 问答；`#DS 问题`：DeepSeek 问答。两者使用独立配置。
- `@bot 随机一题`、`@bot 结算`：按 CF 完整提交历史跳过已 AC 的题目；分配后的首次 AC 可结算一次积分。已通过题目以当前绑定账号的 CF 记录为准，数据库保存当前分配题目和时间。
- `#duel @某人 分数`、`#duel accept/reject/judge/reset`：邀请、应战、结算与状态重置。重置取消自己参与的邀请或单挑，恢复双方可参与状态，积分不变。单挑状态持久化，查询失败不会提前清除状态。
- `@bot 做题汇总`：只展示已绑定姓名和班级且当天至少有一次提交的用户，不限制入学年份，不要求洛谷账号。`@bot 洛谷题单`：要求绑定姓名和洛谷账号；`platforms.luogu.training_max_year_gap` 为 `1` 时还要求绑定班级且当年或上一年入学，为 `null` 时关闭班级年份筛选。两种报表查询期间每5秒汇报实际处理人数，发送图片前汇报最终进度。
- `@bot 签到`、`@bot 待交作业`：月历签到及学习通未交作业。
- `给我看看`：合并转发关键词列表；`来只关键词`：随机发送内容。
- 回复消息后 `添加关键词`：保存文字、图片、视频或音频，成功后回复“添加成功”。
- 每条文字独立保存为一个 UTF-8 文本文件，编号对应单条内容。
- 引用机器人发出的内容发送 `@bot 删除关键词`，或发送 `@bot 删除关键词-编号`：先显示待删除编号，再由同一管理员在同一群于 60 秒内发送 `@bot 确认删除 关键词-编号`。
- `@bot 清空关键词`：显示本次待删除数量，再发送 `@bot 确认清空 关键词`。确认只处理发起时选中的内容，不删除此后新增的内容。`@bot 取消删除` 可取消当前操作。
- 删除和清空限配置中的管理员；确认过期需重新发起。机器人发送成功后按群号、消息 ID 记录对应编号，映射保留 7 天，重启后仍可引用；未记录或过期的消息可按编号操作。编号在 SQLite 中累计递增，删除、清空或重启后均不复用。

## 数据与测试

- `resources/data/bot.db`：用户、积分、分配题目、单挑状态和收藏索引。
- R2：按关键词保存的图片、音视频和文字；SQLite 保存编号与云端路径。
- `output/checkin_calendars/`：用户月历签到图片。
- `resources/images/`：签到使用的日历背景及勾选图标。
- `output/reports/`：生成的统计表和洛谷题单图片。
题库保存在 SQLite 的 `codeforces_problems` 表，字段为 `contest_id`、`problem_index`、`rating`。题库为空时下载并写入；已有题目时直接查询数据库，按难度筛选并排除当前账号已 AC 的题目。

机器人运行期间，题库每天按 `problemset.refresh_time` 更新；任务采用北京时间，不受服务器时区影响。下载成功后事务替换题库，失败保留原数据并记录日志。修改更新时间后重启机器人生效，机器人关闭期间不会执行更新。

洛谷的 18 个训练题单保存在 SQLite 的 `luogu_training_problems` 表，字段为 `training_id`、`problem_id`。数据缺失时首次下载，日常画图直接读取数据库；每天在相同时间检查更新，完整下载成功后统一替换，失败保留旧题单。用户的通过记录仍在生成报告时实时查询。

平台页面结构、接口限流及查询历史数量会影响统计完整性。CF 分页读取完整提交历史；牛客当前页面最多 200 条。网络或解析失败在统计报告中单独标注，避免显示成零提交。测试使用模拟响应，不能替代各平台真实账号验证。Linux QQ 启动尚未在 Linux 实机验证，部署说明见下方 Linux 部署章节。

AtCoder 提交采用分页读取，AC 总次数按提交记录计算，最近提交不局限于今天；接口限速遵循 AtCoder Problems 的要求。参考 https://github.com/kenkoooo/AtCoderProblems/blob/main/doc/api.md 。


测试运行：`python -B -m unittest discover -s tests -v`。测试从配置示例创建虚构配置，使用临时数据库和模拟平台响应，无需填写真实配置或密钥。健康检查：`GET /health`。

## 云端收藏（Cloudflare R2）

注册 Cloudflare 并开通 R2，创建 Standard 私有桶（例如 `bjgbot-collections`）。创建仅有该桶 Object Read & Write 权限的 R2 API 凭据。无需开放公共访问或购买域名。

在 `config/bot_settings.json` 填写 `collections.r2.endpoint`（控制台提供的 S3 endpoint）、`collections.r2.bucket`、`collections.r2.access_key_id` 和 `collections.r2.secret_access_key`，这些字段为必填项。密钥不要提交到版本库。`collections.r2.url_expiry_seconds` 为发送时生成的下载地址有效期，单位秒，每次发送都会重新生成。

收藏内容统一存储在 R2，路径为“关键词/数字.扩展名”，例如 `bjg/12.jpg`。新增内容直接上传，文字直接读取，图片、视频和音频使用临时下载地址；随机发送不显示文件名。删除与清空在确认后操作云端对象。

数据库需要随机器人部署，记录关键词、编号、类型、云端路径、累计编号、消息映射及待确认操作。

官方说明：[R2 入门](https://developers.cloudflare.com/r2/get-started/)、[创建 S3 凭据](https://developers.cloudflare.com/r2/get-started/s3/)。

## Linux 部署

Linux 首次启动时，如果配置中的 QQ 可执行文件不存在，脚本会复用已安装的 NapCat；没有安装时下载官方安装器，安装 NapCat Shell 和匹配的 Linux QQ 到当前用户的 `~/Napcat/`，并将实际路径写回 `config/bot_settings.json`。Windows 的 QQ 和 DLL 不能直接用于 Linux。

Ubuntu/Debian 直接运行 `bash scripts/start.sh`。脚本检查并自动安装缺少的 Python、venv、pip、xvfb、xauth、util-linux、screen、curl 和 sudo；普通用户安装系统依赖时可能需要输入 sudo 密码，依赖齐全时跳过安装。系统软件源需要提供 Python 3.10 或更高版本。其他发行版需自行准备对应依赖。

复制项目时保留数据库、题库、字体、图片、数据目录和配置，不需要复制 Windows 的 .venv。

config/bot_settings.json 中的 napcat.linux_qq_path 可以填写已有安装的路径，例如 ~/Napcat/opt/QQ/qq 或 /opt/QQ/qq；新安装时脚本自动更新此字段。确认 bot.qq、bot.host、bot.port、napcat.api_url、napcat.webui_port 与 NapCat 配置一致。所有机器人运行配置均从 JSON 读取。

官方安装器固定到已核对的版本并校验 SHA256；下载缓存位于 `output/setup/`。安装说明：https://github.com/NapNeko/NapCat-Installer 。

```bash
bash scripts/start.sh
```

首次启动自动创建 .venv-linux 并安装 requirements.txt。部署前需要准备 config/bot_settings.json 并填写账号和路径。PYTHON_BIN 可指定解释器，例如 PYTHON_BIN=python3.12 bash scripts/start.sh。

在 NapCat WebUI 中启用 HTTP 服务端和 HTTP 客户端上报，消息格式使用 array，关闭上报自身消息。示例配置的 API 是 127.0.0.1:5020，上报地址是 http://127.0.0.1:5010/。API Token 与 config/bot_settings.json 中 napcat.api_token 一致。

日志在 logs/napcat.log 和 logs/bjgbot.log。首次登录可能需要扫描 NapCat 日志中的二维码。远程服务器可通过 SSH 转发 WebUI 的配置端口。保持终端运行，Ctrl+C 关闭本次脚本启动的服务；已有服务不会被关闭。

SSH 断开后需要继续运行时，可先用 `bash scripts/start.sh` 完成依赖安装，在服务启动后按 Ctrl+C 停止本次服务，再执行 `screen -S bjgbot bash scripts/start.sh`。按 Ctrl+A 再按 D 离开会话，使用 `screen -r bjgbot` 返回。

此脚本适用于 NapCat Shell 本机部署。

使用 systemd 的服务器可安装 `scripts/systemd/napcat-watchdog.service` 和 `.timer` 到 `/etc/systemd/system/`，执行 `sudo systemctl daemon-reload` 和 `sudo systemctl enable --now napcat-watchdog.timer`。服务文件默认项目位于 `/opt/BJGBOT`，虚拟环境为 `.venv-linux`，NapCat 服务名为 `napcat.service`，其他部署路径需对应修改。每分钟检查 QQ 登录状态，连续三次离线后自动重启一次；两次自动重启至少间隔十分钟，恢复在线后才允许下一轮。若重启后仍未登录，等待扫码，并通过本机原生接口更新即将过期的二维码，不反复重启；已扫码或正在初始化时不替换二维码。手动停止 NapCat 时不自动启动。

## 小内存服务器资源防护

`scripts/systemd/bjgbot-agent-resources.conf` 和 `bjgbot-agent-gateway-resources.conf` 是当前 2GB 云服务器的可选 systemd 限制，分别安装为对应服务的 `service.d/50-resources.conf`。AI 主服务内存软限制 768MiB、硬限制 832MiB、swap 上限 64MiB，并限制实际磁盘读写和 IOPS；异常超限时可能只重启 AI 服务。网关软限制 192MiB、硬限制 256MiB，为 4K 图片传输留出空间；转发时复用原请求字节，不再重新序列化大图 JSON。软限制应高于正常工作内存，避免反复回收导致读盘。QQ 不加内存硬限制。其他配置的服务器需按容量调整，磁盘路径 `/dev/vda` 也需匹配实际设备。

`bjgbot-writeback.conf` 可安装到 `/etc/sysctl.d/`，将后台回写阈值设为 16MiB、脏页上限设为 64MiB，避免集中回写。支持 zswap 的服务器可安装并启用 `bjgbot-zswap.service`，将按需分配的压缩缓存上限设为内存的 15%；启用成功后再安装 `bjgbot-memory.conf` 到 `/etc/sysctl.d/` 并加载，将 swappiness 设为 30。原有 2GiB swap 加上 `/swapfile-bjgbot-extra` 的 2GiB 应急空间，合计约 4GiB，并通过 `/etc/fstab` 持久化；增加 swap 不能替代物理内存，也不保证消除磁盘等待。

`bjgbot-python-resources.conf` 可安装为业务服务的 systemd drop-in，限制绘图计算库的内部线程和分配器 arena。绘图库仅在生成报表时加载，普通启动和题单刷新不加载；统计与题单网络采集最多八条并发，所有用户仍会被处理。生图和发送在 Agent 内按顺序排队，避免多张 4K 图片同时形成内存峰值，不增加聊天冷却、每日额度或回复次数上限。

`bjgbot-resource-monitor.service` 和 `.timer` 安装到 systemd 后启用定时器，每分钟记录内存、swap、I/O 压力、服务读写、匿名页/文件页和文件页重新读入计数，保存在 `output/logs/resource-health.jsonl`，轮转最多约 3MiB，供故障后排查。普通访问日志不逐条记录，警告和错误仍保留；远程附件下载最多同时两条，普通文本不创建临时目录。

## 手机登录页

独立入口只提供 QQ 在线状态、登录二维码和 DS 剩余余额，不开放 OneBot、消息上报或 NapCat 管理后台。默认要求访问密码，登录有效期为七天，二维码禁止缓存并在两分钟后隐藏。密码模式下离线时可主动获取新二维码，保存图片后用手机 QQ 从相册识别。设置 `require_password: false` 可直接访问公开只读页面；此时二维码和余额不再私密，主动重启接口关闭，自动掉线恢复仍然运行。自动重启后仍离线时，后台定时检查并通过本机 WebUI 原生接口更新即将过期的二维码，不重启 QQ；已扫码、初始化或重连期间不替换二维码。

`config/bot_settings.json` 的 `login_page` 保存 `password_hash`（Werkzeug 密码哈希）、`session_secret`（至少 32 字符的随机密钥）和 `qr_path`（NapCat 的 `cache/qrcode.png` 绝对路径）。`host`、`port` 控制监听地址和端口，`secure_cookie` 控制是否只通过 HTTPS 发送登录 Cookie。这些值只保存在被忽略的真实配置中。未配置该部分不影响机器人运行。

服务器将 `scripts/systemd/napcat-login.service` 安装到 `/etc/systemd/system/`，执行 `systemctl daemon-reload` 和 `systemctl enable --now napcat-login.service`。直接通过公网 IP 访问时，配置 `host: "0.0.0.0"`、`port: 5011`、`secure_cookie: false`，并在服务器安全组放行 TCP 5011，使用 `http://服务器IP:5011`；纯 HTTP 不加密密码和二维码。OneBot 和 NapCat 管理后台继续仅监听本机。

示例配置默认仅监听 `127.0.0.1:5011` 且启用安全 Cookie；使用反向代理或官方 cloudflared 和 `napcat-login-tunnel.service` 可提供 HTTPS 入口。临时隧道地址可从 `journalctl -u napcat-login-tunnel.service` 查看，重启隧道后可能变化。

DS 余额通过云端密钥查询 [DeepSeek 余额接口](https://api-docs.deepseek.com/zh-cn/api/get-user-balance/)，每分钟刷新，显示总余额、赠金和充值余额；查询失败单独提示，不显示为零。页面和浏览器均不接收 API 密钥。

余额历史保存在 SQLite 的 `deepseek_balance_samples` 表，每五分钟每币种最多一条，保留 180 天，金额使用十进制文本存储。安装并启用 `scripts/systemd/deepseek-balance-sampler.service` 和 `.timer` 后，即使未打开页面也会采样；打开页面查询余额也会补充当前时间段的记录。页面合并展示当前余额和按天曲线，默认最近 7 天，可自行输入 1 到 180 天；曲线每天一个节点，使用当日最新余额，明细只在后台保存。

统计的是账号总余额的采样变化，包含其他客户端的使用。减少金额是估算，不等同于精确 API 账单，赠金到期或调账也会改变余额；跨日差额按后一次采样归属日期。没有采样的时段不补造数据。更换 DS 密钥或服务地址后使用独立历史序列，防止不同账号混在一起。

## 字体

字体集中在 `resources/fonts/`，随项目部署，Windows 和 Linux 使用同一套资源：

- `SimHei.ttf`：原项目中文字体。
- `NotoSans.ttf`：拉丁文字等补充字形。
- `NotoSansThai.ttf`：泰文及组合标记。
- `NotoSansSymbols2.ttf`：补充符号。

签到图片按完整文本或字符簇选择字体；统计表和题单表启用多字体回退。已有签到图片中的旧文字不会自动重新绘制。字体覆盖有边界，不保证所有 Unicode 字符或彩色 Emoji 都能显示。

Noto 字体来自 Google Fonts 官方仓库，许可文件随字体保存在 `resources/fonts/`：https://github.com/google/fonts 。
