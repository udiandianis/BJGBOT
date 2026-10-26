import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Reply:
    text: str
    forward: bool = False
    on_sent: Callable | None = None


@dataclass(frozen=True)
class Command:
    name: str
    pattern: re.Pattern
    handler: Callable
    help: str
    guard: Callable
    progress: str


class Router:
    def __init__(self):
        """初始化命令注册列表。"""
        self.commands = []

    def register(self, name, pattern, handler, help='', guard=lambda event: True, progress=''):
        """注册完整匹配规则、处理函数、帮助和守卫；拒绝重复名称。"""
        if any(command.name == name for command in self.commands):
            raise ValueError('Duplicate command: ' + name)
        self.commands.append(Command(name, re.compile(pattern, re.I | re.S), handler, help, guard, progress))

    def dispatch(self, event, notify=None):
        """执行第一个匹配且通过守卫的命令，返回 Reply 或 None。"""
        for command in self.commands:
            match = command.pattern.fullmatch(event.text)
            if match and command.guard(event):
                if command.progress and notify:
                    notify(command.progress)
                result = command.handler(event, match)
                return result if isinstance(result, Reply) or result is None else Reply(str(result))
        return None

    def help_text(self):
        """汇总帮助段落，保留同一指令内说明与示例的换行。"""
        return '\n\n'.join(command.help.strip() for command in self.commands if command.help.strip())
