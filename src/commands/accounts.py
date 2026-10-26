from ..storage.users import BINDING_FIELDS


def register(router, services, settings):
    """注册统一的账号绑定和平台查询命令。"""
    def bind(event, match):
        """验证绑定内容，将完整平台名对应到数据库字段。"""
        account_type = match[1].lower()
        value = match[2].strip()
        if not value:
            return '用法：#bind 类型 内容'
        if account_type == 'chaoxing' and len(value.split()) != 2:
            return '用法：#bind chaoxing 账号 密码'
        return services.bind(BINDING_FIELDS[account_type], value, event.user_id)

    def query(event, match):
        """查询显式账号、提及用户或发送者自己绑定的账号。"""
        platform = match[1].lower()
        username = (match[2] or '').strip()
        if username and event.mentions:
            return '请提供账号或 @用户，二者选择其一'
        if username:
            return services.query(platform, username)
        if len(event.mentions) > 1:
            return '每次只能查询一个用户'
        user_id = event.mentions[0] if event.mentions else event.user_id
        return services.query_bound(user_id, BINDING_FIELDS[platform])

    router.register('account.bind', r'#bind\s+(name|class|chaoxing|codeforces|nowcoder|luogu|atcoder)\s+(.*)', bind,
                    '#bind name 姓名：绑定姓名\n例：#bind name 张三\n\n'
                    '#bind class 班级：绑定班级\n例：#bind class 测试班级2302\n\n'
                    '#bind codeforces/nowcoder/luogu/atcoder 账号：绑定平台账号\n例：#bind codeforces zhangsan\n\n'
                    '#bind chaoxing 账号 密码：绑定学习通，密码保存在本机数据库；请留意群内可见性\n例：#bind chaoxing zhangsan 123456')
    router.register('account.query', r'#(codeforces|nowcoder|luogu|atcoder)(?:\s+(.*))?', query,
                    '#codeforces/nowcoder/luogu/atcoder 账号：查询指定账号\n例：#codeforces zhangsan\n\n'
                    '#平台名 @用户：查询该用户；不带账号或提及则查询自己\n例：#codeforces @张三；查询自己：#codeforces')
    router.register('account.mentioned', r'(codeforces|nowcoder|luogu|atcoder)',
                    lambda event, match: services.query_bound(event.mentions[0], BINDING_FIELDS[match[1].lower()]),
                    '@用户 codeforces/nowcoder/luogu/atcoder：查询对方绑定的账号\n例：@张三 codeforces',
                    guard=lambda event: len(event.mentions) == 1)
