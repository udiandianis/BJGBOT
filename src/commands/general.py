from ..router import Reply


def register(router, services, settings):
    """注册本模块的命令、帮助、权限与参数检查。"""
    router.register('help', r'#help', lambda event, match: Reply(router.help_text(), forward=True), '#help：查看所有指令')
    router.register('agent.control', r'#AGENT\s+(?:START|END)', lambda event, match: None,
                    '#AGENT START：机器人管理员开启本群 Agent\n#AGENT END：机器人管理员关闭本群 Agent，原有指令继续可用')
    router.register('contests', r'#近期比赛', lambda event, match: services.contests(), '#近期比赛：查看即将开始的CF和AtCoder比赛')
    router.register('ai.gpt', r'#GPT(?:\s+(.*))?',
                    lambda event, match: services.answer('gpt', match[1].strip()) if match[1] and match[1].strip() else '用法：#GPT 问题',
                    '#GPT 问题：使用配置中的 GPT 服务回答')
    router.register('ai.deepseek', r'#DS(?:\s+(.*))?',
                    lambda event, match: services.answer('deepseek', match[1].strip()) if match[1] and match[1].strip() else '用法：#DS 问题',
                    '#DS 问题：使用配置中的 DeepSeek 服务回答')
