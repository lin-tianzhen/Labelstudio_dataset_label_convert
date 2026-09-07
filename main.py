"""
数据集标注格式转换统一入口

支持将 YOLO / Pascal-VOC / COCO 格式的数据集标注转换为 LabelStudio 可识别的格式。
配置通过 config.yaml 管理，也可通过命令行参数覆盖。

用法:
    python main.py                          # 使用默认 config.yaml
    python main.py --config my_config.yaml  # 指定配置文件
    python main.py --format yolo --dataset-root ./data  # 命令行覆盖
"""
import os
import sys
import argparse

# 确保项目根目录在 sys.path 中（支持从任意目录运行）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

"""数据集格式转换器包"""
from converters.YOLO_convert import convert as yolo_convert
from converters.VOC_convert import convert as voc_convert
from converters.COCO_convert import convert as coco_convert
from converters.AnyLabeling_convert import convert as anylabeling_convert

CONVERTERS = {
    "yolo": yolo_convert,
    "voc": voc_convert,
    "coco": coco_convert,
    "anylabeling": anylabeling_convert,
}
def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    try:
        import yaml
    except ImportError:
        print("[错误] 未安装 PyYAML，请先执行: pip install pyyaml")
        sys.exit(1)

    if not os.path.isfile(config_path):
        print(f"[错误] 配置文件不存在: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    return cfg

def merge_config(config: dict, args: argparse.Namespace) -> dict:
    """将命令行参数合并到配置中（命令行优先级更高）"""
    if args.format:
        config["format"] = args.format
    if args.dataset_root:
        config["dataset_root"] = args.dataset_root
    if args.output:
        config["output_dir"] = args.output
    if args.images_subdir:
        config["images_subdir"] = args.images_subdir
    if args.labels_subdir:
        config["labels_subdir"] = args.labels_subdir
    if args.annotation_json:
        config["annotation_json"] = args.annotation_json
    if args.classes_file:
        config["classes_file"] = args.classes_file
    return config

def validate_config(config: dict) -> None:
    """校验配置项"""
    if "format" not in config or not config["format"]:
        raise ValueError("配置中缺少 'format' 字段 (yolo/voc/coco/anylabeling)")

    fmt = config["format"].lower()
    if fmt not in CONVERTERS:
        raise ValueError(f"不支持的格式 '{config['format']}'，可选: {list(CONVERTERS.keys())}")

    if "dataset_root" not in config or not config["dataset_root"]:
        raise ValueError("配置中缺少 'dataset_root' 字段")

    dataset_root = os.path.abspath(config["dataset_root"])
    if not os.path.isdir(dataset_root):
        raise FileNotFoundError(f"数据集目录不存在: {dataset_root}")

    config["dataset_root"] = dataset_root

    # 输出目录默认值
    output_dir = config.get("output_dir") or os.path.join(dataset_root, "labelstudio_output")
    config["output_dir"] = output_dir

def main():
    parser = argparse.ArgumentParser(
        description="数据集标注格式转换工具 (YOLO/VOC/COCO/AnyLabeling -> LabelStudio)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py
  python main.py --config my_config.yaml
  python main.py --format yolo --dataset-root ./my_yolo_dataset
  python main.py --format coco --dataset-root ./my_coco --annotation-json ./ann.json
        """
    )
    parser.add_argument("--config", "-c", default="config.yaml",
                        help="YAML 配置文件路径 (默认: config.yaml)")
    parser.add_argument("--format", "-f", choices=["yolo", "voc", "coco", "anylabeling"],
                        help="数据集格式 (覆盖配置文件)")
    parser.add_argument("--dataset-root", "-d", help="数据集根目录 (覆盖配置文件)")
    parser.add_argument("--output", "-o", help="输出目录 (覆盖配置文件)")
    parser.add_argument("--images-subdir", help="图片子目录名 (覆盖配置文件)")
    parser.add_argument("--labels-subdir", help="标注子目录名 (覆盖配置文件)")
    parser.add_argument("--annotation-json", help="COCO 标注 JSON 路径 (覆盖配置文件)")
    parser.add_argument("--classes-file", help="YOLO 类别文件路径 (覆盖配置文件)")

    args = parser.parse_args()

    # 1. 加载配置
    config_path = os.path.join(PROJECT_ROOT, args.config)
    if not os.path.isfile(config_path):
        # 尝试相对路径
        config_path = os.path.abspath(args.config)
    print(f"[INFO] 加载配置文件: {config_path}")
    config = load_config(config_path)

    # 2. 合并命令行覆盖
    config = merge_config(config, args)

    # 3. 校验配置
    try:
        validate_config(config)
    except (ValueError, FileNotFoundError) as e:
        print(f"[错误] {e}")
        sys.exit(1)

    fmt = config["format"].lower()
    print(f"\n{'='*60}")
    print(f"  数据集格式 : {fmt.upper()}")
    print(f"  数据集根目录: {config['dataset_root']}")
    print(f"  输出目录   : {config['output_dir']}")
    print(f"{'='*60}\n")

    # 4. 分派到对应转换器
    converter = CONVERTERS[fmt]
    try:
        converter(**config)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n[错误] 转换失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 发生未知错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()