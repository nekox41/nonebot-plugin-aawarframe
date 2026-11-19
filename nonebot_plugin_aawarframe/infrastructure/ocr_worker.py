# Desc: 在独立进程中预处理紫卡图片并运行 PaddleOCR。
# Date: 2026-11-15
# Author: Aameow

import base64
import contextlib
import io
import json
import os
import re
import sys

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")


def preprocess(payload):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 16_000_000
    with Image.open(io.BytesIO(base64.b64decode(payload, validate=True))) as source:
        if source.width * source.height > 16_000_000:
            raise ValueError("图片尺寸过大，请裁剪紫卡区域。")
        picture = ImageOps.exif_transpose(source).convert("RGB")
    scale = min(2.5, 800 / picture.width, 2400 / max(picture.size))
    picture = picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))))
    original = cv2.cvtColor(np.asarray(picture), cv2.COLOR_RGB2BGR)
    return original


def recognize(ocr, image):
    results = []
    for result in ocr.predict(image):
        data = result.json
        if isinstance(data, str):
            data = json.loads(data)
        data = data.get("res", data)
        for text, score, box in zip(data.get("rec_texts", []), data.get("rec_scores", []), data.get("rec_polys", [])):
            results.append({"text": text, "score": float(score), "box": box})
    return results


def variants(ocr, image):
    import cv2
    import numpy as np

    first = recognize(ocr, image)
    yield first
    # 根据文字基线校正轻微倾斜；大角度旋转交给用户重新截图。
    number_boxes = [np.asarray(row["box"], dtype=float) for row in first if re.search(r"[+−－-]\s*\d|[×x]\s*\d", row["text"])]
    if len(number_boxes) >= 2:
        line_height = float(np.median([box[:, 1].max() - box[:, 1].min() for box in number_boxes]))
        top = max(0, int(min(box[:, 1].min() for box in number_boxes) - 8 * line_height))
        bottom = min(image.shape[0], int(max(box[:, 1].max() for box in number_boxes) + 4 * line_height))
        if bottom - top > 50 and bottom - top < image.shape[0] * .85:
            image = image[top:bottom]
            yield recognize(ocr, image)
    angles = []
    for row in first:
        box = np.asarray(row["box"], dtype=float)
        dx, dy = box[1] - box[0]
        if dx > 25:
            angle = float(np.degrees(np.arctan2(dy, dx)))
            if abs(angle) <= 20:
                angles.append(angle)
    angle = float(np.median(angles)) if angles else 0
    corrected = image
    if abs(angle) > 1:
        height, width = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1)
        corrected = cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
        yield recognize(ocr, corrected)
    # 原色不受滤色损失影响，灰度局部增强用于亮光、低对比和锁定图标。
    gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8)).apply(gray)
    yield recognize(ocr, cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR))


def emit(data):
    print("AAWARFRAME_OCR:" + json.dumps(data, ensure_ascii=False), flush=True)


def main():
    with contextlib.redirect_stdout(sys.stderr):
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(
            ocr_version="PP-OCRv5", text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            use_doc_orientation_classify=False, use_doc_unwarping=False,
            use_textline_orientation=True, device="cpu", cpu_threads=2, enable_mkldnn=False,
        )
    emit({"ready": True})
    for line in sys.stdin:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                request = json.loads(line)
                image = preprocess(request["image"])
                if request.get("retry"):
                    output = list(variants(ocr, image))
                else:
                    output = [recognize(ocr, image)]
            emit({"passes": output})
        except Exception as exc:
            emit({"error": str(exc)[:200]})


if __name__ == "__main__":
    main()
