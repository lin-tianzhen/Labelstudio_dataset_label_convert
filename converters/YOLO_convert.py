"""
YOLO 数据集 -> LabelStudio 格式转换器

YOLO 目录结构 (常见):
    dataset/
    ├── images/          # 图片
    ├── labels/          # 标注 .txt (每行: class_id cx cy w h, 归一化 0~1)
    └── classes.txt      # 或 data.yaml (可选，类别列表)

用法:
    python yolo_to_labelstudio.py <dataset_root> [--output <out_dir>]
"""
import os
import sys
import argparse

from converters.utils.labelstudio_utils import (
    scan_images, get_image_size, to_labelstudio_percent,
    make_rectangle_result, make_task, build_image_url,
    save_labelstudio_json, save_labelstudio_xml, summarize
)

def read_classes(classes_file: str) -> list:
    """从 classes.txt (每行一个类别) 读取类别列表"""
    classes = []
    with open(classes_file, 'r', encoding='utf-8') as f:
        for line in f:
            name = line.strip()
            if name:
                classes.append(name)
    return classes

def find_classes_file(dataset_root: str) -> str:
    """在数据集中查找类别文件"""
    candidates = [
        os.path.join(dataset_root, "classes.txt"),
        os.path.join(dataset_root, "data.yaml"),
        os.path.join(dataset_root, "labels", "classes.txt"),
        os.path.join(dataset_root, "names.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return ""

def parse_yolo_label(label_path: str, img_w: int, img_h: int, classes: list) -> list:
    """
    解析单个 YOLO 标注文件，返回 LabelStudio result 列表。
    YOLO 行格式: class_id center_x center_y width height (均归一化 0~1)
    """
    results = []
    with open(label_path, 'r', encoding='utf-8') as f:
        for line_idx, line in enumerate(f):
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            try:
                cls_id = int(parts[0])
                cx = float(parts[1])
                cy = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])
            except ValueError:
                continue

            # 归一化坐标 -> 像素坐标
            cx_px = cx * img_w
            cy_px = cy * img_h
            w_px = w * img_w
            h_px = h * img_h
            # 左上角
            x_px = cx_px - w_px / 2.0
            y_px = cy_px - h_px / 2.0

            label_name = classes[cls_id] if cls_id < len(classes) else f"class_{cls_id}"
            x_pct, y_pct, w_pct, h_pct = to_labelstudio_percent(x_px, y_px, w_px, h_px, img_w, img_h)

            box_id = f"{os.path.splitext(os.path.basename(label_path))[0]}_{line_idx}"
            results.append(make_rectangle_result(box_id, x_pct, y_pct, w_pct, h_pct, label_name))
    return results

def convert(dataset_root: str, output_dir: str) -> None:
    images_dir = os.path.join(dataset_root, "images")
    labels_dir = os.path.join(dataset_root, "labels")

    # ---------- 1. 扫描与检查 ----------
    print("[1/4] 扫描数据集 ...")
    images = scan_images(images_dir)
    if not images:
        print(f"[错误] 在 {images_dir} 未找到图片，请确认目录结构。")
        sys.exit(1)

    # 检查标注文件
    label_files = {}
    missing_labels = []
    for img in images:
        base = os.path.splitext(img)[0]
        label_path = os.path.join(labels_dir, base + ".txt")
        if os.path.isfile(label_path):
            label_files[img] = label_path
        else:
            missing_labels.append(img)

    print(f"      图片数量 : {len(images)}")
    print(f"      找到标注 : {len(label_files)}")
    if missing_labels:
        print(f"      缺少标注 : {len(missing_labels)} 张 (将跳过)")
        for m in missing_labels[:10]:
            print(f"        - {m}")
        if len(missing_labels) > 10:
            print(f"        ... 共 {len(missing_labels)} 张")

    # ---------- 2. 读取类别 ----------
    print("\n[2/4] 读取类别配置 ...")
    classes_file = find_classes_file(dataset_root)
    if classes_file:
        classes = read_classes(classes_file)
        print(f"      类别文件: {classes_file}")
    else:
        # 从标注中自动推断类别
        print("      未找到 classes.txt，将从标注文件中自动推断类别 ...")
        max_cls = -1
        for lp in label_files.values():
            with open(lp, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        try:
                            max_cls = max(max_cls, int(parts[0]))
                        except ValueError:
                            pass
        classes = [f"class_{i}" for i in range(max_cls + 1)]
    print(f"      类别数量 : {len(classes)}")
    print(f"      类别列表 : {classes}")

    # ---------- 3. 转换标注 ----------
    print("\n[3/4] 转换标注 ...")
    tasks = []
    for idx, img in enumerate(images):
        if img not in label_files:
            continue
        img_path = os.path.join(images_dir, img)
        size = get_image_size(img_path)
        if size is None:
            print(f"      [跳过] 无法读取图片尺寸: {img}")
            continue
        img_w, img_h = size
        results = parse_yolo_label(label_files[img], img_w, img_h, classes)
        image_url = build_image_url(img)
        tasks.append(make_task(image_url, results))
        if (idx + 1) % 50 == 0:
            print(f"      已处理 {idx + 1}/{len(images)} ...")

    # ---------- 4. 输出 ----------
    print("\n[4/4] 生成 LabelStudio 文件 ...")
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "labelstudio_annotations.json")
    xml_path = os.path.join(output_dir, "labelstudio_config.xml")
    save_labelstudio_json(tasks, json_path)
    save_labelstudio_xml(classes, xml_path)
    summarize(classes, images, tasks)

def main():
    parser = argparse.ArgumentParser(description="YOLO -> LabelStudio 转换工具")
    parser.add_argument("dataset_root", help="YOLO 数据集根目录 (需包含 images/ 和 labels/)")
    parser.add_argument("--output", "-o", default=None,
                        help="输出目录 (默认: 数据集根目录/labelstudio_output)")
    args = parser.parse_args()

    dataset_root = os.path.abspath(args.dataset_root)
    output_dir = args.output or os.path.join(dataset_root, "labelstudio_output")

    if not os.path.isdir(dataset_root):
        print(f"[错误] 数据集目录不存在: {dataset_root}")
        sys.exit(1)

    convert(dataset_root, output_dir)

if __name__ == "__main__":
    main()