# 作用：复现游戏赏金使用的整数随机序列及洗牌规则。
# 编写日期：2026-11-10
# 作者：Aameow


class SeededRandom:
    def __init__(self, seed: int):
        self.seed = seed & 0xFFFFFFFFFFFFFFFF

    def integer(self, minimum: int, maximum: int) -> int:
        if maximum < minimum:
            raise ValueError("随机数范围为空")
        if minimum == maximum:
            return minimum
        self.seed = (0x5851F42D4C957F2D * self.seed + 0x14057B7EF767814F) & 0xFFFFFFFFFFFFFFFF
        return minimum + ((self.seed >> 32) & 0x3FFFFFFF) % (maximum - minimum + 1)

    def shuffle(self, values: list) -> None:
        for size in range(len(values), 1, -1):
            index = self.integer(0, size - 1)
            values[index], values[size - 1] = values[size - 1], values[index]

    def choice(self, values: list):
        return values[self.integer(0, len(values) - 1)]
