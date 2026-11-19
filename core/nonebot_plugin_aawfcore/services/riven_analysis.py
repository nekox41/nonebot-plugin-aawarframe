# Desc: 合并紫卡 OCR 文字，匹配武器词条并计算相对均值评级。
# Date: 2026-11-15
# Author: Aameow

import re
import unicodedata
from bisect import bisect_right

from ..grq import get_grq
from ..grq.normalizer import normalize_name
from ..localization.riven_attributes import attribute_names, attributes, normalize_attribute
from ..models.common import Card, Section
from ..models.errors import UserInputError
from .riven_values import CLASS_NAMES, RivenValuesService, numerical_value

NUMBER = re.compile(r"(?<![A-Za-z0-9])(?P<sign>[+−－﹣-]|[×x])\s*(?P<value>\d+(?:[.,，。]\d+)?)\s*(?P<unit>[%％]?)")
ANNOTATION = re.compile(r"[（(].*?(?:[）)]|$)")


def text_rows(rows):
    lines = []
    # 行框中心分组，使被锁图标或列间隙拆开的数字和描述重新合并。
    for item in sorted(rows, key=lambda r: sum(p[1] for p in r["box"]) / 4):
        box = item["box"]
        y = sum(p[1] for p in box) / 4
        height = max(p[1] for p in box) - min(p[1] for p in box)
        x = min(p[0] for p in box)
        group = next((line for line in reversed(lines) if abs(line["y"] - y) < max(5, min(line["height"], height) * .45)), None)
        if group is None:
            group = {"y": y, "height": height, "parts": []}
            lines.append(group)
        group["parts"].append((x, unicodedata.normalize("NFKC", item["text"]), item["score"]))
    return [(" ".join(p[1] for p in sorted(line["parts"])), min(p[2] for p in line["parts"])) for line in lines]


def parse_stats(lines):
    header, records = [], []
    for text, confidence in lines:
        match = NUMBER.search(text)
        # 容量、段位、循环次数均无正负号，不参与强化等级判定。
        if match:
            if confidence < .65:
                raise UserInputError("词条文字不够清晰，请裁剪紫卡区域后重发。")
            value_text = re.sub(r"[,，。]", ".", match["value"])
            value = float(value_text)
            if match["sign"] in {"-", "−", "－", "﹣"}:
                value = -value
            records.append({"value": value, "factor": match["sign"] in {"×", "x"}, "digits": len(value_text.split(".")[1]) if "." in value_text else 0, "text": text[match.end():]})
        elif records:
            # 只接续当前词条；装备需求和循环次数不可能成为新词条。
            records[-1]["text"] += text
        elif confidence >= .7:
            header.append(text)
    if not 2 <= len(records) <= 4:
        raise UserInputError("未识别到完整词条，请保留武器名称和全部词条后重发。")
    for record in records:
        text = normalize_attribute(ANNOTATION.sub("", record["text"]))
        found = [(name, slug) for name, slug in attribute_names() if name in text and len(name) >= 2]
        if not found:
            raise UserInputError("有词条未能识别，请换一张清晰图片。")
        # 全名优先于二字缩写，避免“异常状态伤害”误落到“伤害”。
        record["attribute"] = attributes()[found[0][1]]
        if record["factor"] and record["attribute"]["unit"] != "faction":
            raise UserInputError("词条数值格式不明确，请重新截图。")
    if len({r["attribute"]["id"] for r in records}) != len(records):
        raise UserInputError("有词条重复或未识别完整，请重新截图。")
    return header, records


def weapon_from_header(header):
    grq = get_grq()
    words = [normalize_name(line) for line in header]
    matches = {}
    for name, ids in grq.domains["Riven"].names.items():
        if name and any(word.startswith(name) for word in words):
            for resource_id in ids:
                matches[resource_id] = max(matches.get(resource_id, 0), len(name))
    if matches:
        longest = max(matches.values())
        selected = [key for key, size in matches.items() if size == longest]
        if len(selected) == 1:
            return grq.get("Riven", selected[0])
    for line in reversed(header):
        name = re.split(r"[A-Za-z]", line)[0].strip()
        result = grq.search("Riven", name)
        if result.resource:
            return result.resource
    raise UserInputError("无法确定武器名称，请保留武器名称并重新截图。")


def display(attribute, value):
    unit = attribute["unit"]
    if unit == "faction":
        return f"×{1 + value:.2f}"
    return f"{value:+.1f}" + ("" if unit == "flat" else unit)


class RivenAnalysisService:
    def __init__(self, ocr):
        self.ocr = ocr
        self.values = RivenValuesService()

    async def query(self, image, arguments=""):
        arguments = arguments.strip()
        rank = None
        if arguments:
            match = re.fullmatch(r"([0-8])级", arguments)
            if arguments == "满级":
                rank = 8
            elif match:
                rank = int(match[1])
            else:
                raise UserInputError("用法：分析 [满级/0级至8级]，附上或引用一张紫卡图片。")
        return await self.ocr.recognize(image, lambda rows: self.analyze(rows, rank))

    def analyze(self, rows, forced_rank=None):
        header, records = parse_stats(text_rows(rows))
        weapon = weapon_from_header(header)
        kind = weapon.metadata.get("weapon_type")
        if kind not in CLASS_NAMES:
            kind = weapon.metadata.get("rivenType")
        kind = {"kitgun": "pistol", "zaw": "melee"}.get(kind, kind)
        if kind not in CLASS_NAMES:
            raise UserInputError("暂缺该武器类型的数值资料。")
        family = self.values.family(weapon)
        if not family:
            raise UserInputError("暂缺该武器的完整资料，请更新资源。")
        # 按系数及显示方向判断增益；派系倍率先扣除基准 1。
        for record in records:
            attribute = record["attribute"]
            if attribute["unit"] == "faction":
                if not record["factor"]:
                    raise UserInputError("派系伤害倍率未能识别，请重新截图。")
                record["value"] -= 1
            coefficient = attribute["coefficients"].get(kind)
            if coefficient is None:
                raise UserInputError("识别到不符合武器类型的词条，请重新截图。")
            direction = coefficient * (-1 if attribute["inverse"] else 1)
            record["positive"] = record["value"] * direction > 0
            if attribute["coefficients"].get(kind) is None or not attribute["positive" if record["positive"] else "negative"] or (kind == "melee" and attribute["id"] == "Visi" and not record["positive"]):
                raise UserInputError("识别到不符合武器类型的词条，请重新截图。")
        positives = sum(r["positive"] for r in records)
        layout = f"{positives}+{len(records) - positives}"
        if layout not in self.values.rules["layouts"]:
            raise UserInputError("词条数量或正负号未能识别，请重新截图。")
        ordinary, spliced = self.values.attributes(family[0], weapon, family, layout, kind)
        available = {a.name.split("（")[0] for a in [*ordinary, *spliced]}
        for record in records:
            name = record["attribute"]["name"]
            if name not in available and not (kind == "melee" and record["attribute"]["id"] in {"Croni", "Crita"}):
                raise UserInputError("词条与武器不符，请重新截图。")
        multipliers = self.values.rules["layouts"][layout]
        disposition = self.values.rules["disposition"]
        candidates = []
        for rank in ([forced_rank] if forced_rank is not None else range(9)):
            means = [numerical_value(r["attribute"], kind, multipliers[0 if r["positive"] else 1], disposition, rank) for r in records]
            if all(abs(r["value"] - mean) <= abs(mean) * .1 + .5 * 10 ** -r["digits"] + .00001 for r, mean in zip(records, means)):
                candidates.append((rank, means))
        if not candidates:
            raise UserInputError("数值超出正常范围，请确认截图清晰、词条完整，且不是已装备后的面板。")
        if len(candidates) != 1:
            raise UserInputError("仅凭图片无法确定强化等级，请发送“分析 满级”或“分析 0级”等并附上图片。")
        rank, means = candidates[0]
        output = []
        for record, mean in zip(records, means):
            delta = (abs(record["value"]) / abs(mean) - 1) * 100
            score = delta if record["positive"] else -delta
            grade = "FEDCBAS"[bisect_right([-7, -4, -1, 1, 4, 7], score)]
            attribute = record["attribute"]
            name = attribute["name"] + ("（负面）" if not record["positive"] else "")
            output.append([name, display(attribute, record["value"]), display(attribute, mean), f"{delta:+.2f}%", grade])
        return Card(
            title=weapon.name(), source="紫卡分析", analysis_mode=True,
            sections=[Section(title=f"{CLASS_NAMES[kind]} · {layout} · {rank}级", columns=["词条", "识别数值", "均值", "偏差", "评级"], rows=output)],
            notes=["按截图显示值估算；负面惩罚越小，评级越高。"],
        )
