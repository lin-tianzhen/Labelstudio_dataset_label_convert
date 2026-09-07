"""
AnyLabeling 数据集 -> LabelStudio 格式转换器

AnyLabeling 导出的 JSON 格式 (每张图片一个 JSON 文件):
{
  "name": "image.png",
  "objects": [
    {
      "label": "Wrench",
      "polygon": [[x1, y1], [x2, y2], ...]
    },
    {
      "label": "cat",
      "rectangle": [x, y, width, height]
    }
  ]
}

支持的标注类型:
  - polygon   -> LabelStudio polygonlabels
  - rectangle -> LabelStudio rectanglelabels

用法:
    python AnyLabeling_convert.py <dataset_root> [--output <out_dir>]
"""
import os
import sys
import json

from converters.utils.labelstudio_utils import (
    scan_images, get_image_size, to_labelstudio_percent, points_to_percent,
    make_rectangle_result, make_polygon_result, make_task, build_image_url,
    save_labelstudio_json, save_labelstudio_xml, summarize, IMAGE_EXTS
)


def find_images_dir(dataset_root: str) -> str:
    """自动查找图片目录"""
    candidates = ["images", "JPEGImages", "Images", "image", "img"]
    for name in candidates:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p) and scan_images(p):
            return p
    # 检查根目录是否有图片
    if scan_images(dataset_root):
        return dataset_root
    return os.path.join(dataset_root, "images")


def find_label_dir(dataset_root: str) -> str:
    """自动查找 AnyLabeling 标注目录"""
    candidates = ["labels", "Annotations", "annotations", "json", "labelme"]
    for name in candidates:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p):
            json_count = sum(1 for f in os.listdir(p) if f.lower().endswith('.json'))
            if json_count > 0:
                return p
    # 检查根目录是否有 JSON
    root_json = sum(1 for f in os.listdir(dataset_root) if f.lower().endswith('.json'))
    if root_json > 0:
        return dataset_root
    return dataset_root


def parse_anylabeling_json(json_path: str) -> dict:
    """解析单个 AnyLabeling JSON 文件"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_image_for_json(json_path: str, images_dir: str) -> str:
    """根据 JSON 文件名查找对应的图片"""
    base = os.path.splitext(os.path.basename(json_path))[0]
    for ext in IMAGE_EXTS:
        img_path = os.path.join(images_dir, base + ext)
        if os.path.isfile(img_path):
            return os.path.basename(img_path)
        img_path = os.path.join(images_dir, base + ext.upper())
        if os.path.isfile(img_path):
            return os.path.basename(img_path)
    return ""


def convert(dataset_root: str, output_dir: str,
            images_subdir: str = None, labels_subdir: str = None,
            **kwargs) -> None:
    """
    AnyLabeling -> LabelStudio 转换入口。

    Args:
        dataset_root: 数据集根目录
        output_dir: 输出目录
        images_subdir: 图片子目录名 (None=自动查找, "."=根目录)
        labels_subdir: 标注子目录名 (None=自动查找, "."=根目录)
        **kwargs: 兼容其他格式的配置项，忽略
    """
    # 确定图片目录
    if images_subdir and images_subdir != ".":
        images_dir = os.path.join(dataset_root, images_subdir)
    elif images_subdir == ".":
        images_dir = dataset_root
    else:
        images_dir = find_images_dir(dataset_root)

    # 确定标注目录
    if labels_subdir and labels_subdir != ".":
        labels_dir = os.path.join(dataset_root, labels_subdir)
    elif labels_subdir == ".":
        labels_dir = dataset_root
    else:
        labels_dir = find_label_dir(dataset_root)

    # ---------- 1. 扫描与检查 ----------
    print("[1/4] 扫描数据集 ...")
    images = scan_images(images_dir)
    if not images:
        # 自动回退: 尝试在整个数据集根目录下查找图片
        fallback_images = scan_images(dataset_root)
        if fallback_images:
            print(f"      [提示] {images_dir} 下无图片，回退到根目录: {dataset_root}")
            images_dir = dataset_root
            images = fallback_images
        else:
            raise FileNotFoundError(
                f"在 {images_dir} 及 {dataset_root} 下均未找到图片。"
                f"\n请检查目录结构，或在 config.yaml 中设置 images_subdir。"
                f"\n常见 AnyLabeling 结构: 图片和 JSON 在同一目录，或 images/ + labels/。"
            )

    json_files = []
    if os.path.isdir(labels_dir):
        for fname in os.listdir(labels_dir):
            if fname.lower().endswith('.json'):
                json_files.append(os.path.join(labels_dir, fname))
    json_files.sort()

    print(f"      图片目录 : {images_dir}")
    print(f"      标注目录 : {labels_dir}")
    print(f"      图片数量 : {len(images)}")
    print(f"      JSON 数量: {len(json_files)}")

    if not json_files:
        raise FileNotFoundError(f"在 {labels_dir} 未找到 JSON 标注文件。")

    image_set = set(images)

    # ---------- 2. 解析所有 JSON，收集类别与标注类型 ----------
    print("\n[2/4] 解析标注文件，提取类别 ...")
    all_classes = set()
    annotation_types = set()
    parsed_data = []

    for jf in json_files:
        try:
            data = parse_anylabeling_json(jf)
        except Exception as e:
            print(f"      [警告] 解析失败 {os.path.basename(jf)}: {e}")
            continue

        objects = data.get("objects", [])
        image_filename = data.get("name", "")
        if not image_filename or image_filename not in image_set:
            image_filename = find_image_for_json(jf, images_dir)

        if not image_filename:
            print(f"      [跳过] 未找到对应图片: {os.path.basename(jf)}")
            continue

        for obj in objects:
            label = obj.get("label", "")
            if label:
                all_classes.add(label)
            if "polygon" in obj:
                annotation_types.add("polygon")
            if "rectangle" in obj:
                annotation_types.add("rectangle")

        parsed_data.append((jf, image_filename, objects))

    classes = sorted(all_classes)
    print(f"      类别数量 : {len(classes)}")
    print(f"      类别列表 : {classes}")
    print(f"      标注类型 : {annotation_types if annotation_types else '未检测到'}")
    print(f"      有效样本 : {len(parsed_data)}")

    if not annotation_types:
        print("[警告] 未检测到 polygon 或 rectangle 标注，结果可能为空。")

    # ---------- 3. 转换标注 ----------
    print("\n[3/4] 转换标注 ...")
    tasks = []
    for idx, (jf, image_filename, objects) in enumerate(parsed_data):
        img_path = os.path.join(images_dir, image_filename)
        size = get_image_size(img_path)
        if size is None:
            print(f"      [跳过] 无法读取图片尺寸: {image_filename}")
            continue
        img_w, img_h = size

        results = []
        for bi, obj in enumerate(objects):
            label = obj.get("label", "unknown")
            base_id = f"{os.path.splitext(image_filename)[0]}_{bi}"

            if "polygon" in obj:
                points_px = obj["polygon"]
                points_pct = points_to_percent(points_px, img_w, img_h)
                results.append(make_polygon_result(base_id, points_pct, label))

            if "rectangle" in obj:
                rect = obj["rectangle"]
                x_px, y_px, w_px, h_px = rect[0], rect[1], rect[2], rect[3]
                x_pct, y_pct, w_pct, h_pct = to_labelstudio_percent(
                    x_px, y_px, w_px, h_px, img_w, img_h)
                results.append(make_rectangle_result(base_id, x_pct, y_pct, w_pct, h_pct, label))

        image_url = build_image_url(image_filename)
        tasks.append(make_task(image_url, results))
        if (idx + 1) % 50 == 0:
            print(f"      已处理 {idx + 1}/{len(parsed_data)} ...")

    # ---------- 4. 输出 ----------
    print("\n[4/4] 生成 LabelStudio 文件 ...")
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "labelstudio_annotations.json")
    xml_path = os.path.join(output_dir, "labelstudio_config.xml")

    ann_types = sorted(annotation_types) if annotation_types else ["polygon"]
    save_labelstudio_json(tasks, json_path)
    save_labelstudio_xml(classes, xml_path, annotation_types=ann_types)
    summarize(classes, images, tasks)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AnyLabeling -> LabelStudio 转换工具")
    parser.add_argument("dataset_root", help="AnyLabeling 数据集根目录 (需包含 images/ 和标注 JSON)")
    parser.add_argument("--output", "-o", default=None,
                        help="输出目录 (默认: 数据集根目录/labelstudio_output)")
    args = parser.parse_args()

    dataset_root = os.path.abspath(args.dataset_root)
    output_dir = args.output or os.path.join(dataset_root, "labelstudio_output")

    if not os.path.isdir(dataset_root):
        print(f"[错误] 数据集目录不存在: {dataset_root}")
        sys.exit(1)

    try:
        convert(dataset_root, output_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"[错误] {e}")
        sys.exit(1)