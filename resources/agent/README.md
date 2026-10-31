# 大肥鱼社区 Agent

使用 [Aurabot](https://github.com/accomplish07zrh-eng/dsh-aurabot-qq/tree/062f3653df7091344756168078f28ea87934d9c0)（MIT，1.0.3）和 DeepSeek Harness 0.2.1-rc.2。人格卡、聊天策略、记忆和会话压缩沿用社区机制。接入层添加群开关、现有业务指令说明和 NapCat 转接；没有重新实现 Agent，也没有额外的每小时/每天配额或固定 30 条上下文。

## 使用

- Agent 管理员从 `config/bot_settings.json` 的 `collections.admins` 首位读取，在目标群发送 `#AGENT START` 开启该群，`#AGENT END` 关闭该群；群主和群管理员身份不会额外获得权限。社区只支持一个 `ownerQQ`；修改该列表首位并重启 Python 和 Agent 服务后生效。
- 默认所有群关闭。群开关保存在社区的 `allow.groups` 中，重启仍保留。关闭不删除历史记忆。
- 开启后沿用社区接话规则：@机器人，或默认称呼“大肥鱼”“肥鱼”；普通聊天是否接话也由社区策略决定。
- [插话配置补丁](community/group-interjection.patch)将基础插话概率设为 30%，心情和话题相关度加权后最高 90%。默认取消主动插话的间隔和每小时次数上限；`group.cooldownSec`、`group.maxPerHour` 为 `0` 表示不限制，概率上限由 `group.interjectMaxChance` 配置。夜间静默和续聊沿用原有策略。现有部署的设置保存在社区配置中，常规部署不会覆盖。
- [话题加权补丁](community/topic-weighting.patch)将 `group.minRelevance` 默认设为 `0`，取消话题硬门槛，普通话题也有基础参与机会；相关度加权独立保留。插话判定概率为 `min(最高概率, 基础概率 × 心情系数 × (1 + 4 × 相关度))`，因此更相关的话题仍更容易触发。触发后大肥鱼继续按原生规则决定是否接话或保持沉默。续聊也不再因相关度低而被门槛拦截。
- [短时回复限制补丁](community/optional-burst-limit.patch)允许 `group.burstMax=0` 关闭短时回复次数限制，首次配置默认关闭；普通成员的 @、主动插话和续聊均不会因近期回复过多被拦截。设置为正数时可重新启用，现有部署保留配置文件中的值。
- 原有 `#bind`、查询、积分、单挑、签到、收藏、`#GPT`、`#DS` 等指令优先执行。Agent 获得当前 `#help` 的说明，能告诉群友如何使用。
- 社区权限身份沿用上述机器人管理员，仅用于权限判断；日常按昵称交流，不另设“主人”或“管理员”等称谓。私聊范围、其他原生命令、语音和表情设置均由社区配置处理。

配置脚本应用 [权限身份适配补丁](community/permission-only.patch)：统一工具说明、上下文和结果中的权限用语，移除记忆整理中的主仆关系前提、管理员专用聊天提示和情绪加权。低落心情改用轻微委屈的语气，不引导挖苦或辱骂；输入情绪识别词表与输出口吻分开。管理员仍按 `ownerQQ` 校验操作权限；专属主动私聊保持关闭。原始社区人格卡仅作为未启用的参考保留。

[空消息补丁](community/empty-message.patch)将无正文消息中不准确的“图片/表情”占位改为“没有正文”，避免单独 @机器人时误以为收到了图片；真正的图片仍由社区解析并交给 DeepSeek。

[图片上下文补丁](community/quoted-and-recent-images.patch)补取同一聊天中被引用消息的图片，并在群聊实际请求模型时带上本段近期消息中的图片，支持先发图再 @机器人询问。沿用社区每次最多四张图片的处理范围；不会从其他群或私聊补图。

按本次部署约定，管理员私聊保留社区 `full` 权限，包含 Shell 和文件工具；远端 Agent 以 `root` 运行，DSH 使用原生 `danger-full-access` 部署模式，因此能直接操作服务器。群聊使用社区 `social` 权限，没有这些本地工具。

长期记忆使用社区自带的索引检索、人物档案和定时整理机制；原版内部有 3000 条自动清理阈值，并非之前草案里的 50 条硬上限。会话上下文由 DSH 管理并压缩，不再以本项目自定义的消息条数截断。

人格使用社区原生管理面板 **Aurabot → 人格** 编辑、保存和切换，下一轮回复生效。仓库提供 [软萌鲸鱼人格卡](personas/dafeiyu-casual.md)：爱白米饭、有点小迷糊和小委屈，语气温柔俏皮，认真求助时可靠。角色背景参考用户提供的图片，以及[社区角色文档](https://github.com/YunYueSama/codex-deepseek-pet/blob/main/docs/%E8%A7%92%E8%89%B2%E8%AE%BE%E5%AE%9A.md)、[鲸鱼娘人格项目](https://github.com/Kaalia0912/dsh-whale-musume-persona)中的二创特征，以本项目人格卡为准，不宣称官方定稿。原版人格仍保留；实际启用项和编辑后的内容由社区数据目录保存，常规部署不会覆盖。

## 模型和能力

复用 `config/bot_settings.json` 的 `ai.deepseek` 地址、模型和 Key，不需要另配 GPT。原有 `#GPT` 是既有独立功能。社区支持的生图、翻唱等功能需要各自的模型或运行环境，不会因为加载了模块就自动可用。空间发布、B 站互动和向管理员定时推送未配置，首次接入默认关闭；其余尽量保留原版默认值。

模型使用 DSH 原生 `deepseek-official` 适配器和官方当前名称 `deepseek-flash`，直接获得图文、工具调用、推理和上下文能力声明；不另外维护一份模型能力表。原配置的 `deepseek-chat` 已实测由官方服务端映射到 Flash，配置脚本会更新为正式名称，Key 不变。

图片直接交给 DeepSeek Flash 识别，没有额外的 GPT 识图服务。语音依赖社区 TTS/ASR 的可用性；原版内置语音安装器和本机语音回退偏向 Windows，本次 Linux 部署未配置语音和翻唱服务。

生图使用社区内置的 `qq_draw_image`：在社区面板“生图”页选择接口类型，配置服务地址、模型和 Key，开启后按描述生成图片并发送到当前聊天。Gemini 地址使用 `/v1beta` 前缀，OpenAI 兼容服务使用 `/v1` 前缀。凭据保存在被 Git 忽略的社区配置中，聊天模型仍可使用 DeepSeek。`imageGen.ownerOnly=false` 允许已开启群聊和允许私聊中的普通用户请求画图，首次配置默认关闭“仅管理员可画图”；服务器工具权限仍按管理员身份校验。[发送结果补丁](community/image-send-result.patch)确保 QQ 发送失败时不误报成功。

[多服务生图补丁](community/image-backend-fallback.patch)支持 Gemini 原生 `generateContent` 和 OpenAI 兼容生图接口。`imageGen` 是首选，`imageGen.fallbacks` 中的服务按数组顺序备用；当前顺序为 Gemini Pro Image、Gemini Flash Image、Grok Imagine Quality。网络错误、超时、未返回有效图片时切换，成功立即停止；明确的内容拒绝不会触发绕过重试。全部失败时只把失败事实交给大肥鱼，由当前人格自然回应，技术错误记入后台日志。面板不回传任何首选或备用服务的完整 Key，普通保存会保留凭据。

[高分辨率补丁](community/image-highest-resolution.patch)让 `imageGen.resolution` 真正进入生图请求，默认 `4K`，备用服务可以单独配置。当前两个 Gemini 均固定请求 4K，已实测返回 4096×4096 图片；Grok 使用 Quality 型号并请求其最高 2K，使用原生 `resolution`、`aspect_ratio` 参数，不传其他模型的尺寸和画质参数。当前 Grok 转发服务实测会忽略分辨率或比例设置，因此请求 2K 不代表实际返回 2K，也不会通过本地放大伪装高分辨率。部署为生图请求预留 180 秒超时，服务失败后的切换顺序保持不变。

[辅助识图扩展](vision-assist/index.mjs)给大肥鱼提供 `qq_inspect_image`。收到图片但拿不准细节、文字或动漫角色时，先请 Gemini 检查；失败或仍不确定时再请 Grok 核对，再由大肥鱼组织最终回复。复用生图服务配置的凭据，辅助模型默认为 `gemini-3.8-flash-high` 和 `grok-4.7`，可在社区扩展设置中调整；聊天主模型仍为 DeepSeek。图片缓存按聊天隔离，只用于近期追问；没有附件不会调用辅助模型，也不保证能辨认每一个角色。

群聊和允许的私聊通过原生扩展 [联网找表情包](web-stickers/index.mjs) 获得搜索能力，不需要额外 API Key。例如“找一张委屈猫猫的表情包”：先搜索 Bing 图片，把候选图片交给模型看，再选择发送并保存到社区表情库。当前使用搜索引擎的预览图，动图可能变为静态；搜索无结果或发送失败时如实反馈。此扩展只下载搜索预览，不给群聊开放服务器文件、Shell 或通用网址访问；可以在社区面板的扩展页关闭。

## Linux 远端部署

目前安装位置为 `/opt/BJGBOT`，已有 Python 环境 `.venv-linux` 和运行中的 NapCat。安装与配置脚本只处理本机运行文件，不发送 QQ 消息：

```sh
cd /opt/BJGBOT
.venv-linux/bin/python scripts/setup_agent_remote.py
.venv-linux/bin/python scripts/configure_agent_remote.py
cp resources/agent/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bjgbot-agent-gateway bjgbot-agent
systemctl restart bjgbot
```

安装脚本固定 Node 24.22.1、DSH 和 Aurabot 版本，并核验官方 Node SHA256。运行时与记忆位于 `.agent/`，不进入 Git。配置脚本复用既有 Key，备份配置到 `output/deployment/pre-agent-*`，后续执行保留已开启的群和社区设置。配置中的可选 `agent` 节只需要 `enabled`、`base_url`、`token`；旧配置不包含这一节时 Agent 不启用。

进程分工：原 Python 服务负责现有业务和消息分流；`bjgbot-agent` 运行原版 DSH/Aurabot；`bjgbot-agent-gateway` 将社区使用的 OneBot 接口转到现有 NapCat，避免重复上报。新增端口 3080、5030 只监听 `127.0.0.1`，内部转接需要令牌。

```sh
systemctl status bjgbot bjgbot-agent bjgbot-agent-gateway napcat
journalctl -u bjgbot-agent -n 50 --no-pager
```

停用时先 `systemctl stop bjgbot-agent bjgbot-agent-gateway`，再将 `agent.enabled` 设为 `false` 并重启 `bjgbot`；原业务和原数据库独立保留。需要访问社区管理面板时，通过 SSH 转发本机端口到远端 `127.0.0.1:3080`，不要直接暴露到公网。
