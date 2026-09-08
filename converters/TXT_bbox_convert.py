"""
TXT-BBox 数据集 -> LabelStudio 格式转换器

TXT 标注格式 (每张图片对应一个 txt 文件):
    每行: image_filename class_name x1 y1 x2 y2
    其中 (x1, y1) 为左上角像素坐标, (x2, y2) 为右下角像素坐标

目录结构 (常见):
    dataset/
    ├── images/          # 图片
    └── labels/          # 标注 .txt

用法:
    python TXT_bbox_convert.py <dataset_root> [--output <out_dir>]
"""
import os
import sys
import argparse

from converters.utils.labelstudio_utils import (
    scan_images, get_image_size, to_labelstudio_percent,
    make_rectangle_result, make_task, build_image_url,
    save_labelstudio_json, save_labelstudio_xml, summarize
)

def find_images_dir(dataset_root: str) -> str:
    """自动查找图片目录"""
    for name in ["images", "JPEGImages", "Images", "image", "img","train_image","test_image"]:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p) and scan_images(p):
            return p
    if scan_images(dataset_root):
        return dataset_root
    return os.path.join(dataset_root, "images")

def find_labels_dir(dataset_root: str) -> str:
    """自动查找标注目录"""
    for name in ["labels", "Annotations", "annotations", "label","train_annotation","test_annotation"]:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p):
            txt_count = sum(1 for f in os.listdir(p) if f.lower().endswith('.txt'))
            if txt_count > 0:
                return p
    root_txt = sum(1 for f in os.listdir(dataset_root) if f.lower().endswith('.txt'))
    if root_txt > 0:
        return dataset_root
    return os.path.join(dataset_root, "labels")

def parse_txt_label(label_path: str, img_w: int, img_h: int) -> list:
    """
    解析单个 TXT 标注文件，返回 LabelStudio result 列表。
    行格式: image_filename class_name x1 y1 x2 y2
    """
    results = []
    base = os.path.splitext(os.path.basename(label_path))[0]
    with open(label_path, 'r', encoding='utf-8') as f:
        for line_idx, line in enumerate(f):
            parts = line.strip().split()
            if len(parts) < 6:
                continue
            try:
                label_name = parts[1]
                x1 = float(parts[2])
                y1 = float(parts[3])
                x2 = float(parts[4])
                y2 = float(parts[5])
            except ValueError:
                continue

            w_px = x2 - x1
            h_px = y2 - y1
            x_pct, y_pct, w_pct, h_pct = to_labelstudio_percent(x1, y1, w_px, h_px, img_w, img_h)

            box_id = f"{base}_{line_idx}"
            results.append(make_rectangle_result(box_id, x_pct, y_pct, w_pct, h_pct, label_name))
    return results

def convert(dataset_root: str, output_dir: str,
            images_subdir: str = None, labels_subdir: str = None,
            **kwargs) -> None:
    """
    TXT-BBox -> LabelStudio 转换入口。

    Args:
        dataset_root: 数据集根目录
        output_dir: 输出目录
        images_subdir: 图片子目录名 (None=自动查找, "."=根目录)
        labels_subdir: 标注子目录名 (None=自动查找, "."=根目录)
        **kwargs: 兼容其他格式的配置项，忽略
    """
    if images_subdir and images_subdir != ".":
        images_dir = os.path.join(dataset_root, images_subdir)
    elif images_subdir == ".":
        images_dir = dataset_root
    else:
        images_dir = find_images_dir(dataset_root)

    if labels_subdir and labels_subdir != ".":
        labels_dir = os.path.join(dataset_root, labels_subdir)
    elif labels_subdir == ".":
        labels_dir = dataset_root
    else:
        labels_dir = find_labels_dir(dataset_root)

    # ---------- 1. 扫描与检查 ----------
    print("[1/4] 扫描数据集 ...")
    images = scan_images(images_dir)
    if not images:
        fallback_images = scan_images(dataset_root)
        if fallback_images:
            print(f"      [提示] {images_dir} 下无图片，回退到根目录: {dataset_root}")
            images_dir = dataset_root
            images = fallback_images
        else:
            print(f"[错误] 在 {images_dir} 未找到图片，请确认目录结构。")
            sys.exit(1)

    label_files = {}
    missing_labels = []
    for img in images:
        base = os.path.splitext(img)[0]
        label_path = os.path.join(labels_dir, base + ".txt")
        if os.path.isfile(label_path):
            label_files[img] = label_path
        else:
            missing_labels.append(img)

    print(f"      图片目录 : {images_dir}")
    print(f"      标注目录 : {labels_dir}")
    print(f"      图片数量 : {len(images)}")
    print(f"      找到标注 : {len(label_files)}")
    if missing_labels:
        print(f"      缺少标注 : {len(missing_labels)} 张 (将跳过)")
        for m in missing_labels[:10]:
            print(f"        - {m}")
        if len(missing_labels) > 10:
            print(f"        ... 共 {len(missing_labels)} 张")

    # ---------- 2. 提取类别 ----------
    print("\n[2/4] 提取类别 (遍历所有 TXT) ...")
    class_set = set()
    for label_path in label_files.values():
        with open(label_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    class_set.add(parts[1])
    classes = sorted(class_set)
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
        results = parse_txt_label(label_files[img], img_w, img_h)
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
    parser = argparse.ArgumentParser(description="TXT-BBox -> LabelStudio 转换工具")
    parser.add_argument("dataset_root", help="TXT-BBox 数据集根目录 (需包含 images/ 和 labels/)")
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
