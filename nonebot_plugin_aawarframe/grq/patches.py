# 作用：合并来源资料与人工补充，支持删除指定字段。
# 编写日期：2026-11-13
# 作者：Aameow


def merge(base, patch, delete_null=True):
    result = dict(base)
    for key, value in patch.items():
        if value is None and delete_null:
            result.pop(key, None)
            continue
        result[key] = (
            merge(result.get(key, {}), value, delete_null)
            if isinstance(value, dict) and isinstance(result.get(key, {}), dict)
            else value
        )
    return result
