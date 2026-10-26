def register(router, services, settings):
    """注册本模块的命令、帮助、权限与参数检查。"""
    def duel(event, match):
        """解析单挑操作或评分，验证目标后调用单挑服务。"""
        argument = match[1].strip().lower()
        if not event.mentions and argument in ('accept', 'reject', 'judge', 'reset'):
            return services.duel(event.group_id, argument, event.user_id)
        if len(event.mentions) == 1 and argument.isdigit():
            rating = int(argument)
            if event.mentions[0] == event.user_id:
                return '不能挑战自己'
            if 800 <= rating <= 3500 and rating % 100 == 0:
                return services.invite(event.group_id, event.user_id, event.mentions[0], rating)
            return 'rating范围应该是800-3500之间的整百数'
        return '用法：#duel @某人 800-3500，或 #duel accept/reject/judge/reset'

    router.register('duel', r'#duel(?:\s+(.*))?',
                    lambda event, match: duel(event, match) if match[1] is not None else '用法：#duel @某人 分数 或 #duel accept/reject/judge/reset',
                    '#duel @某人 分数：双方须绑定CF，分数为800-3500整百数\n例：#duel @张三 1200\n\n'
                    '#duel accept：被挑战者在邀请群接受单挑\n例：#duel accept\n\n'
                    '#duel reject：被挑战者在邀请群拒绝单挑\n例：#duel reject\n\n'
                    '#duel judge：在单挑群结算；无人完成也结束单挑，双方积分不变\n例：#duel judge\n\n'
                    '#duel reset：取消自己参与的邀请或单挑，恢复参与状态，双方积分不变\n例：#duel reset')
