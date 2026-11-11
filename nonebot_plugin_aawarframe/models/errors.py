# 作用：实现 models 层的 errors 功能。
# 编写日期：2026-11-07
# 作者：Aameow


class UserInputError(ValueError):
    """可直接展示给用户的参数错误。"""


class WikiChallengeError(RuntimeError):
    """Wiki 访问被浏览器验证页拦截。"""
