def register(router, services, settings):
    """注册本模块的命令、帮助、权限与参数检查。"""
    actions = [
        ('practice.random', r'随机一题', lambda event: services.random_problem(event.user_id),
         '@bot 随机一题：按CF评分选题，范围800-3500，跳过已AC题目；重新查询会替换当前题目\n例：@bot 随机一题'),
        ('practice.settle', r'结算', lambda event: services.judge_problem(event.user_id),
         '@bot 结算：检查分配题目之后的首次AC并增加机器人积分；重复结算不会重复加分\n例：@bot 结算'),
        ('training.report', r'洛谷题单', lambda event: services.training_report(event.group_id),
         '@bot 洛谷题单：查看已绑定姓名、洛谷账号和班级且符合入学年份条件用户的题单完成情况，每5秒汇报进度\n例：@bot 洛谷题单'),
        ('chaoxing.homework', r'(?:待交作业|我的学习通)', lambda event: services.pending_homework(event.user_id),
         '@bot 待交作业：返回已绑定学习通账号最近到期的最多5项未交作业\n例：@bot 待交作业'),
        ('statistics.table', r'做题汇总', lambda event: services.statistics(event.group_id),
         '@bot 做题汇总：查看已绑定姓名且今日有提交用户的AC提交数/总提交数，每5秒汇报进度；未绑定和查询失败单独标注\n例：@bot 做题汇总'),
        ('checkin', r'(?:签到|🦌)', lambda event: services.checkin(event.raw),
         '@bot 签到：在个人月历上标记今天，同日重复签到不会重复累计\n例：@bot 签到'),
    ]
    progress = {
        'training.report': '正在查询洛谷题单并生成图片，人数较多时可能需要一些时间，请稍候。',
        'statistics.table': '正在查询各平台做题记录并生成汇总图片，人数较多时可能需要一些时间，请稍候。',
    }
    for name, pattern, action, description in actions:
        router.register(name, pattern, lambda event, match, action=action: action(event), description,
                        guard=lambda event: event.mentions == (settings.bot_qq,), progress=progress.get(name, ''))
