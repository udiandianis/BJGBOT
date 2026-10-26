from ..router import Reply


def register(router, services, settings):
    """注册本模块的命令、帮助、权限与参数检查。"""
    router.register('media.list', r'给我\s*看看', lambda event, match: Reply(services.media.list(), forward=True), '给我看看：合并转发可用关键词列表\n例：给我看看')
    router.register('media.random', r'来只\s*(.*)', lambda event, match: services.media.random(match[1], event.group_id), '来只关键词：随机发送一张图片、一段视频、音频或文字\n例：来只猫猫')
    router.register('media.clear', r'清空\s*(.*)', lambda event, match: services.media.request_clear(match[1], event), '@bot 清空关键词：清空该关键词下的内容，仅管理员可用，按提示确认\n例：@bot 清空猫猫', guard=lambda event: event.mentions == (settings.bot_qq,))
    router.register('media.add', r'添加\s*(.*)', lambda event, match: services.media.add(match[1], event.reply_id),
                    '回复原消息后发送 添加关键词：保存图片、视频、音频或文字\n例：引用一张图片，发送 添加猫猫', guard=lambda event: event.reply_id is not None)
    router.register('media.delete', r'删除\s*(.*)', lambda event, match: services.media.request_delete(match[1], event),
                    '@bot 删除关键词：引用要删除的内容；仅管理员可用，按提示确认\n例：引用要删除的消息，发送 @bot 删除猫猫', guard=lambda event: event.mentions == (settings.bot_qq,))
    router.register('media.confirm', r'确认(删除|清空)\s+(.+)', lambda event, match: services.media.confirm(match[1], match[2], event),
                    guard=lambda event: event.mentions == (settings.bot_qq,))
    router.register('media.cancel', r'取消删除', lambda event, match: services.media.cancel(event),
                    guard=lambda event: event.mentions == (settings.bot_qq,))
