class UserInputError(ValueError):
    """可直接展示给用户的参数错误。"""


class WikiChallengeError(RuntimeError):
    """Wiki 访问被浏览器验证页拦截。"""
