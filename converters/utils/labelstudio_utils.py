"""
LabelStudio 格式转换共享工具模块
- 生成 LabelStudio 可识别的 JSON 标注文件
- 生成 LabelStudio 可识别的 XML 类别配置文件
- 坐标转换与文件扫描工具
"""
import os
import json
from typing import List, Dict, Tuple, Optional, Union

# 预定义的类别背景色列表，用于 XML 配置文件
LABEL_COLORS = [
    "green", "blue", "red", "yellow", "purple", "orange", "cyan", "magenta",
    "lime", "pink", "olive", "brown", "navy", "teal", "maroon", "silver",
    "gold", "violet", "coral", "turquoise", "indigo", "crimson", "khaki",
    "orchid", "salmon", "peru", "slateblue", "seagreen", "darkorange", "steelblue"
]

# 支持的图片扩展名
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

def scan_images(images_dir: str) -> List[str]:
    """扫描图片目录，返回排序后的图片文件名列表"""
    if not os.path.isdir(images_dir):
        return []
    files = [
        f for f in os.listdir(images_dir)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ]
    return sorted(files)

def get_image_size(image_path: str) -> Optional[Tuple[int, int]]:
    """
    获取图片尺寸 (width, height)。
    优先使用 PIL，若未安装则使用纯 Python 解析常见格式。
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size  # (width, height)
    except ImportError:
        pass
    except Exception:
        pass

    # 纯 Python 兜底：仅支持 JPEG/PNG
    ext = os.path.splitext(image_path)[1].lower()
    try:
        if ext in ('.jpg', '.jpeg'):
            return _get_jpeg_size(image_path)
        elif ext == '.png':
            return _get_png_size(image_path)
    except Exception:
        pass
    return None

def _get_jpeg_size(filepath: str) -> Optional[Tuple[int, int]]:
    """不依赖 PIL 解析 JPEG 尺寸"""
    with open(filepath, 'rb') as f:
        data = f.read()
    # JPEG SOI marker
    if not data.startswith(b'\xff\xd8'):
        return None
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF markers (start of frame)
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[i + 5:i + 7], 'big')
            width = int.from_bytes(data[i + 7:i + 9], 'big')
            return (width, height)
        seg_len = int.from_bytes(data[i + 2:i + 4], 'big')
        i += 2 + seg_len
    return None

def _get_png_size(filepath: str) -> Optional[Tuple[int, int]]:
    """不依赖 PIL 解析 PNG 尺寸"""
    with open(filepath, 'rb') as f:
        data = f.read(33)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return None
    width = int.from_bytes(data[16:20], 'big')
    height = int.from_bytes(data[20:24], 'big')
    return (width, height)

def to_labelstudio_percent(x: float, y: float, w: float, h: float,
                           img_w: int, img_h: int) -> Tuple[float, float, float, float]:
    """
    将像素坐标 (左上角 x,y + 宽高) 转换为 LabelStudio 百分比坐标 (0-100)。
    """
    if img_w <= 0 or img_h <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    x_pct = (x / img_w) * 100.0
    y_pct = (y / img_h) * 100.0
    w_pct = (w / img_w) * 100.0
    h_pct = (h / img_h) * 100.0
    return (x_pct, y_pct, w_pct, h_pct)

def make_rectangle_result(box_id: str, x: float, y: float, w: float, h: float,
                          label: str) -> Dict:
    """构造单个 rectanglelabels 标注结果对象"""
    return {
        "id": box_id,
        "type": "rectanglelabels",
        "from_name": "label",
        "to_name": "image",
        "value": {
            "x": round(x, 4),
            "y": round(y, 4),
            "width": round(w, 4),
            "height": round(h, 4),
            "rectanglelabels": [label]
        }
    }

def points_to_percent(points: List[List[float]], img_w: int, img_h: int) -> List[List[float]]:
    """
    将像素坐标的多边形点列表转换为 LabelStudio 百分比坐标 (0-100)。
    points: [[x1, y1], [x2, y2], ...]
    """
    if img_w <= 0 or img_h <= 0:
        return [[0.0, 0.0] for _ in points]
    return [[round((p[0] / img_w) * 100.0, 4), round((p[1] / img_h) * 100.0, 4)] for p in points]


def make_polygon_result(poly_id: str, points: List[List[float]], label: str) -> Dict:
    """构造单个 polygonlabels 标注结果对象 (points 为百分比坐标)"""
    return {
        "id": poly_id,
        "type": "polygonlabels",
        "from_name": "polylabel",
        "to_name": "image",
        "value": {
            "points": points,
            "polygonlabels": [label]
        }
    }


def make_task(image_url: str, results: List[Dict]) -> Dict:
    """构造单个 LabelStudio task"""
    return {
        "data": {
            "image": image_url
        },
        "predictions": [
            {
                "result": results
            }
        ]
    }

def build_image_url(image_filename: str, images_subdir: str = "images") -> str:
    """
    构造 LabelStudio 中可引用的图片 URL。
    约定数据集导入后图片位于 ./images/ 下，使用本地文件协议。
    """
    return f"/data/local-files/?d=./{images_subdir}/{image_filename}"

def save_labelstudio_json(tasks: List[Dict], output_path: str) -> None:
    """保存 LabelStudio JSON 标注文件"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)
    print(f"[OK] 已生成 LabelStudio 标注文件: {output_path} (共 {len(tasks)} 条任务)")

def save_labelstudio_xml(classes: List[str], output_path: str,
                         image_name: str = "image",
                         annotation_types: Union[str, List[str]] = "rectangle") -> None:
    """
    生成 LabelStudio 可识别的 XML 类别配置文件。

    Args:
        classes: 类别列表
        output_path: 输出 XML 路径
        image_name: Image 组件名
        annotation_types: 标注类型, 可为 'rectangle' / 'polygon' / ['rectangle', 'polygon']
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if isinstance(annotation_types, str):
        annotation_types = [annotation_types]

    lines = ["<View>",
             f'  <Image name="{image_name}" value="${image_name}"/>']

    if "rectangle" in annotation_types:
        lines.append(f'  <RectangleLabels name="label" toName="{image_name}">')
        for idx, cls in enumerate(classes):
            color = LABEL_COLORS[idx % len(LABEL_COLORS)]
            lines.append(f'    <Label value="{cls}" background="{color}"/>')
        lines.append("  </RectangleLabels>")

    if "polygon" in annotation_types:
        lines.append(f'  <PolygonLabels name="polylabel" toName="{image_name}">')
        for idx, cls in enumerate(classes):
            color = LABEL_COLORS[idx % len(LABEL_COLORS)]
            lines.append(f'    <Label value="{cls}" background="{color}"/>')
        lines.append("  </PolygonLabels>")

    lines.append("</View>")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] 已生成 LabelStudio 类别配置文件: {output_path} (共 {len(classes)} 个类别)" +
          f" [标注类型: {', '.join(annotation_types)}]")

def summarize(classes: List[str], images: List[str], tasks: List[Dict]) -> None:
    """打印转换摘要"""
    total_boxes = sum(len(t.get("predictions", [{}])[0].get("result", [])) for t in tasks)
    print("\n" + "=" * 60)
    print("转换完成摘要")
    print("=" * 60)
    print(f"  类别数量  : {len(classes)}")
    print(f"  类别列表  : {classes}")
    print(f"  图片数量  : {len(images)}")
    print(f"  任务数量  : {len(tasks)}")
    print(f"  标注框总数: {total_boxes}")
    print("=" * 60)