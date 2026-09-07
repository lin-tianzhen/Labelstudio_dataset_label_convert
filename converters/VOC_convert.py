"""
Pascal-VOC 数据集 -> LabelStudio 格式转换器

VOC 目录结构 (常见):
    dataset/
    ├── JPEGImages/       # 图片 (或 images/)
    └── Annotations/      # 标注 .xml (含 object/bndbox xmin/ymin/xmax/ymax)

用法:
    python voc_to_labelstudio.py <dataset_root> [--output <out_dir>]
"""
import os
import sys
import argparse
import xml.etree.ElementTree as ET

from converters.utils.labelstudio_utils import (
    scan_images, get_image_size, to_labelstudio_percent,
    make_rectangle_result, make_task, build_image_url,
    save_labelstudio_json, save_labelstudio_xml, summarize, IMAGE_EXTS
)

def find_images_dir(dataset_root: str) -> str:
    """查找图片目录"""
    for name in ["JPEGImages", "images", "Images", "JPEGimages"]:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p):
            return p
    return os.path.join(dataset_root, "JPEGImages")

def find_annotations_dir(dataset_root: str) -> str:
    """查找标注目录"""
    for name in ["Annotations", "annotations", "Annotations_xml"]:
        p = os.path.join(dataset_root, name)
        if os.path.isdir(p):
            return p
    return os.path.join(dataset_root, "Annotations")

def parse_voc_xml(xml_path: str) -> tuple:
    """
    解析单个 VOC XML，返回 (objects, width, height)。
    objects: list of dict {name, xmin, ymin, xmax, ymax}
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size_elem = root.find("size")
    width = height = 0
    if size_elem is not None:
        w_elem = size_elem.find("width")
        h_elem = size_elem.find("height")
        if w_elem is not None and w_elem.text:
            width = int(float(w_elem.text))
        if h_elem is not None and h_elem.text:
            height = int(float(h_elem.text))

    objects = []
    for obj in root.findall("object"):
        name_elem = obj.find("name")
        bbox = obj.find("bndbox")
        if name_elem is None or bbox is None:
            continue
        name = name_elem.text.strip()

        def _f(tag):
            e = bbox.find(tag)
            return float(e.text) if e is not None and e.text else 0.0

        xmin, ymin = _f("xmin"), _f("ymin")
        xmax, ymax = _f("xmax"), _f("ymax")
        objects.append({
            "name": name,
            "xmin": xmin, "ymin": ymin,
            "xmax": xmax, "ymax": ymax
        })
    return objects, width, height

def convert(dataset_root: str, output_dir: str) -> None:
    images_dir = find_images_dir(dataset_root)
    ann_dir = find_annotations_dir(dataset_root)

    # ---------- 1. 扫描与检查 ----------
    print("[1/4] 扫描数据集 ...")
    images = scan_images(images_dir)
    if not images:
        print(f"[错误] 在 {images_dir} 未找到图片，请确认目录结构。")
        sys.exit(1)

    # 匹配标注文件 (VOC 标注文件名通常与图片同名, 扩展名 .xml)
    label_files = {}
    missing_labels = []
    for img in images:
        base = os.path.splitext(img)[0]
        xml_path = os.path.join(ann_dir, base + ".xml")
        if os.path.isfile(xml_path):
            label_files[img] = xml_path
        else:
            missing_labels.append(img)

    print(f"      图片目录 : {images_dir}")
    print(f"      标注目录 : {ann_dir}")
    print(f"      图片数量 : {len(images)}")
    print(f"      找到标注 : {len(label_files)}")
    if missing_labels:
        print(f"      缺少标注 : {len(missing_labels)} 张 (将跳过)")

    # ---------- 2. 提取类别 ----------
    print("\n[2/4] 提取类别 (遍历所有 XML) ...")
    class_set = set()
    for xml_path in label_files.values():
        try:
            objs, _, _ = parse_voc_xml(xml_path)
            for o in objs:
                class_set.add(o["name"])
        except Exception as e:
            print(f"      [警告] 解析失败 {os.path.basename(xml_path)}: {e}")
    classes = sorted(class_set)
    print(f"      类别数量 : {len(classes)}")
    print(f"      类别列表 : {classes}")

    # ---------- 3. 转换标注 ----------
    print("\n[3/4] 转换标注 ...")
    tasks = []
    for idx, img in enumerate(images):
        if img not in label_files:
            continue
        try:
            objects, xml_w, xml_h = parse_voc_xml(label_files[img])
        except Exception as e:
            print(f"      [跳过] 解析失败 {img}: {e}")
            continue

        # 优先使用 XML 中的尺寸，否则读取图片
        img_w, img_h = xml_w, xml_h
        if img_w <= 0 or img_h <= 0:
            size = get_image_size(os.path.join(images_dir, img))
            if size is None:
                print(f"      [跳过] 无法获取尺寸: {img}")
                continue
            img_w, img_h = size

        results = []
        for bi, o in enumerate(objects):
            x_px = o["xmin"]
            y_px = o["ymin"]
            w_px = o["xmax"] - o["xmin"]
            h_px = o["ymax"] - o["ymin"]
            x_pct, y_pct, w_pct, h_pct = to_labelstudio_percent(x_px, y_px, w_px, h_px, img_w, img_h)
            box_id = f"{os.path.splitext(img)[0]}_{bi}"
            results.append(make_rectangle_result(box_id, x_pct, y_pct, w_pct, h_pct, o["name"]))

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
    parser = argparse.ArgumentParser(description="Pascal-VOC -> LabelStudio 转换工具")
    parser.add_argument("dataset_root", help="VOC 数据集根目录")
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