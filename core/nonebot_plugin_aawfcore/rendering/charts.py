# Desc: 将成交时间序列转换为价格折线和成交量柱状图坐标。
# Date: 2026-11-14
# Author: Aameow

from datetime import timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def axis_number(value):
    if value >= 10000:
        return f"{value / 10000:.1f}".rstrip("0").rstrip(".") + "万"
    return f"{value:.0f}" if value >= 100 else f"{value:.2f}".rstrip("0").rstrip(".")


def trend_chart(period):
    points = period.points
    prices = [p.price for p in points if p.price is not None]
    low, high = min(prices, default=0), max(prices, default=1)
    padding = max((high - low) * 0.1, high * 0.05, 0.1)
    low, high = max(0, low - padding), high + padding
    maximum = max(1, max(p.volume for p in points))
    unit = 880 / len(points)
    path, dots, bars = [], [], []
    connected = False
    for i, point in enumerate(points):
        x = 80 + (i + 0.5) * unit
        if point.price is not None:
            y = 220 - (point.price - low) / (high - low) * 180
            path.append(f"{'L' if connected else 'M'}{x:.2f},{y:.2f}")
            dots.append({"x": x, "y": y})
            connected = True
        else:
            connected = False
        if point.volume:
            height = point.volume / maximum * 65
            bars.append({"x": x - unit * 0.35, "y": 345 - height, "width": unit * 0.7, "height": height})
    ticks = []
    for i in range(5):
        index = round(i * (len(points) - 1) / 4)
        time = points[index].time.astimezone(BEIJING)
        ticks.append({"x": 80 + (index + 0.5) * unit, "text": time.strftime("%m-%d %H时" if len(points) == 48 else "%m-%d"), "anchor": "start" if i == 0 else "end" if i == 4 else "middle"})
    return {
        "path": " ".join(path), "dots": dots, "bars": bars, "ticks": ticks,
        "prices": [{"y": 220 - i * 90, "text": axis_number(low + (high - low) * i / 2)} for i in range(3)],
        "volume_max": axis_number(maximum),
    }
