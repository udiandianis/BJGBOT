# 大肥鱼社区 Agent

使用 [Aurabot 原版](https://github.com/accomplish07zrh-eng/dsh-aurabot-qq/tree/062f3653df7091344756168078f28ea87934d9c0)（MIT，1.0.3）和 DeepSeek Harness 0.2.1-rc.2。原版人格、提示词、聊天策略、记忆和会话压缩均由社区代码处理。这里只添加群开关、现有业务指令说明和 NapCat 转接；没有重新实现 Agent，也没有额外的每小时/每天配额或固定 30 条上下文。

## 使用

- Agent 管理员从 `config/bot_settings.json` 的 `collections.admins` 首位读取，在目标群发送 `#AGENT START` 开启该群，`#AGENT END` 关闭该群；群主和群管理员身份不会额外获得权限。社区只支持一个 `ownerQQ`；修改该列表首位并重启 Python 和 Agent 服务后生效。
- 默认所有群关闭。群开关保存在社区的 `allow.groups` 中，重启仍保留。关闭不删除历史记忆。
- 开启后沿用社区接话规则：@机器人，或默认称呼“大肥鱼”“肥鱼”；普通聊天是否接话也由社区策略决定。
- 原有 `#bind`、查询、积分、单挑、签到、收藏、`#GPT`、`#DS` 等指令优先执行。Agent 获得当前 `#help` 的说明，能告诉群友如何使用。
- 社区权限身份沿用上述机器人管理员；默认称呼设为“管理员”，原生 `ownerName` 可在社区权限面板调整。私聊范围、其他原生命令、语音和表情设置均由社区配置处理。

按本次部署约定，管理员私聊保留社区 `full` 权限，包含 Shell 和文件工具；远端 Agent 以 `root` 运行，DSH 使用原生 `danger-full-access` 部署模式，因此能直接操作服务器。群聊使用社区 `social` 权限，没有这些本地工具。

长期记忆使用社区自带的索引检索、人物档案和定时整理机制；原版内部有 3000 条自动清理阈值，并非之前草案里的 50 条硬上限。会话上下文由 DSH 管理并压缩，不再以本项目自定义的消息条数截断。

人格使用社区原生管理面板 **Aurabot → 人格** 编辑、保存和切换，下一轮回复生效。仓库提供 [日常群友人格卡](personas/dafeiyu-casual.md)：短句、口语、自然接梗，认真问题正常解释。原版人格仍保留；实际启用项和编辑后的内容由社区数据目录保存，常规部署不会覆盖。

## 模型和能力

复用 `config/bot_settings.json` 的 `ai.deepseek` 地址、模型和 Key，不需要另配 GPT。原有 `#GPT` 是既有独立功能。社区支持的生图、翻唱等功能需要各自的模型或运行环境，不会因为加载了模块就自动可用。空间发布、B 站互动和向管理员定时推送未配置，首次接入默认关闭；其余尽量保留原版默认值。

模型使用 DSH 原生 `deepseek-official` 适配器和官方当前名称 `deepseek-flash`，直接获得图文、工具调用、推理和上下文能力声明；不另外维护一份模型能力表。原配置的 `deepseek-chat` 已实测由官方服务端映射到 Flash，配置脚本会更新为正式名称，Key 不变。

图片直接交给 DeepSeek Flash 识别，没有额外的 GPT 识图服务。语音依赖社区 TTS/ASR 的可用性；原版内置语音安装器和本机语音回退偏向 Windows，本次 Linux 部署未配置语音、生图和翻唱服务。

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
