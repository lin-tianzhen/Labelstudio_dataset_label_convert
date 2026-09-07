"""
COCO 数据集 -> LabelStudio 格式转换器

COCO 目录结构 (常见):
    dataset/
    ├── images/                   # 图片
    └── annotations/              # JSON 标注
        ├── instances_train.json
        ├── instances_val.json
        └── ...

COCO bbox 格式: [x, y, width, height] (像素, 左上角)

用法:
    python coco_to_labelstudio.py <dataset_root> <annotation_json> [--output <out_dir>]
"""
import os
import sys
import json
import argparse

from converters.utils.labelstudio_utils import (
    scan_images, get_image_size, to_labelstudio_percent,
    make_rectangle_result, make_task, build_image_url,
    save_labelstudio_json, save_labelstudio_xml, summarize
)

def load_coco(json_path: str) -> dict:
    """加载 COCO JSON"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_annotation_json(dataset_root: str) -> str:
    """自动查找 COCO 标注 JSON"""
    ann_dir = os.path.join(dataset_root, "annotations")
    candidates = []
    if os.path.isdir(ann_dir):
        for f in os.listdir(ann_dir):
            if f.endswith(".json"):
                candidates.append(os.path.join(ann_dir, f))
    # 根目录下的 json
    for f in os.listdir(dataset_root):
        if f.endswith(".json"):
            candidates.append(os.path.join(dataset_root, f))
    candidates.sort()
    return candidates[0] if candidates else ""

def convert(dataset_root: str, annotation_json: str, output_dir: str) -> None:
    images_dir = os.path.join(dataset_root, "images")

    # ---------- 1. 扫描与检查 ----------
    print("[1/5] 扫描数据集 ...")
    images = scan_images(images_dir)
    print(f"      图片目录 : {images_dir}")
    print(f"      图片数量 : {len(images)}")

    if not os.path.isfile(annotation_json):
        print(f"[错误] 标注文件不存在: {annotation_json}")
        sys.exit(1)
    print(f"      标注文件 : {annotation_json}")

    # ---------- 2. 加载 COCO ----------
    print("\n[2/5] 加载 COCO JSON ...")
    coco = load_coco(annotation_json)
    coco_images = coco.get("images", [])
    coco_anns = coco.get("annotations", [])
    coco_cats = coco.get("categories", [])

    # 建立索引
    img_id_to_info = {img["id"]: img for img in coco_images}
    cat_id_to_name = {cat["id"]: cat["name"] for cat in coco_cats}

    # 按 image_id 分组标注
    anns_by_image = {}
    for ann in coco_anns:
        iid = ann["image_id"]
        anns_by_image.setdefault(iid, []).append(ann)

    print(f"      COCO 图片数 : {len(coco_images)}")
    print(f"      COCO 标注数 : {len(coco_anns)}")
    print(f"      COCO 类别数 : {len(coco_cats)}")

    # ---------- 3. 提取类别 ----------
    print("\n[3/5] 提取类别 ...")
    # 按 category id 排序，保证稳定
    sorted_cats = sorted(coco_cats, key=lambda c: c["id"])
    classes = [c["name"] for c in sorted_cats]
    print(f"      类别数量 : {len(classes)}")
    print(f"      类别列表 : {classes}")

    # ---------- 4. 匹配本地图片并转换 ----------
    print("\n[4/5] 转换标注 ...")
    # 本地图片文件名索引
    local_images = set(images)
    filename_to_image = {os.path.basename(img): img for img in images}

    tasks = []
    matched = 0
    for img_info in coco_images:
        file_name = img_info.get("file_name", "")
        base_name = os.path.basename(file_name)

        # 必须在本地 images 目录存在
        if base_name not in filename_to_image:
            continue
        matched += 1

        img_w = img_info.get("width", 0)
        img_h = img_info.get("height", 0)
        # 若 COCO 中无尺寸，则读取本地图片
        if not img_w or not img_h:
            size = get_image_size(os.path.join(images_dir, base_name))
            if size:
                img_w, img_h = size

        if not img_w or not img_h:
            print(f"      [跳过] 无法获取尺寸: {base_name}")
            continue

        results = []
        for bi, ann in enumerate(anns_by_image.get(img_info["id"], [])):
            bbox = ann.get("bbox", [0, 0, 0, 0])  # [x, y, w, h]
            cat_id = ann.get("category_id", -1)
            label_name = cat_id_to_name.get(cat_id, f"class_{cat_id}")
            x_px, y_px, w_px, h_px = bbox[0], bbox[1], bbox[2], bbox[3]
            x_pct, y_pct, w_pct, h_pct = to_labelstudio_percent(x_px, y_px, w_px, h_px, img_w, img_h)
            box_id = f"{img_info['id']}_{bi}"
            results.append(make_rectangle_result(box_id, x_pct, y_pct, w_pct, h_pct, label_name))

        image_url = build_image_url(base_name)
        tasks.append(make_task(image_url, results))

    print(f"      匹配本地图片: {matched}/{len(coco_images)}")

    # ---------- 5. 输出 ----------
    print("\n[5/5] 生成 LabelStudio 文件 ...")
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "labelstudio_annotations.json")
    xml_path = os.path.join(output_dir, "labelstudio_config.xml")
    save_labelstudio_json(tasks, json_path)
    save_labelstudio_xml(classes, xml_path)
    summarize(classes, images, tasks)

def main():
    parser = argparse.ArgumentParser(description="COCO -> LabelStudio 转换工具")
    parser.add_argument("dataset_root", help="COCO 数据集根目录 (需包含 images/)")
    parser.add_argument("annotation_json", nargs="?", default=None,
                        help="COCO 标注 JSON 路径 (不填则自动查找)")
    parser.add_argument("--output", "-o", default=None,
                        help="输出目录 (默认: 数据集根目录/labelstudio_output)")
    args = parser.parse_args()

    dataset_root = os.path.abspath(args.dataset_root)
    if not os.path.isdir(dataset_root):
        print(f"[错误] 数据集目录不存在: {dataset_root}")
        sys.exit(1)

    annotation_json = args.annotation_json or find_annotation_json(dataset_root)
    if not annotation_json:
        print("[错误] 未找到 COCO 标注 JSON，请手动指定路径。")
        sys.exit(1)

    output_dir = args.output or os.path.join(dataset_root, "labelstudio_output")
    convert(dataset_root, annotation_json, output_dir)

if __name__ == "__main__":
    main()