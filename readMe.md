
```markdown
# LabelStudio Dataset Label Convert

将 YOLO / Pascal-VOC / COCO / AnyLabeling 格式的数据集标注转换为 [Label Studio](https://labelstud.io/) 可识别的格式。

## 支持的转换

| 源格式 | 标注类型 | 输出 |
|--------|---------|------|
| **YOLO** | 矩形框 (归一化坐标) | LabelStudio JSON + XML |
| **Pascal VOC** | 矩形框 (XML bndbox) | LabelStudio JSON + XML |
| **COCO** | 矩形框 (JSON bbox) | LabelStudio JSON + XML |
| **AnyLabeling** | 矩形框 + 多边形 | LabelStudio JSON + XML |

## 项目结构

```

Labelstudio_dataset_label_convert/
├── main.py                          # 统一入口
├── config.yaml                      # 配置文件
├── converters/
│   ├── YOLO_convert.py              # YOLO → LabelStudio
│   ├── VOC_convert.py               # VOC → LabelStudio
│   ├── COCO_convert.py              # COCO → LabelStudio
│   ├── AnyLabeling_convert.py       # AnyLabeling → LabelStudio
│   └── utils/
│       └── labelstudio_utils.py     # 共享工具 (坐标转换、JSON/XML 生成等)
├── formatDemo/                      # LabelStudio 输出格式示例
│   ├── labelstudio_label_demo.json  # 标注 JSON 示例
│   ├── labelstudio_classes_demo.xml # 类别配置 XML 示例
│   └── AnyLabeling_label_demo.json  # AnyLabeling 输入示例
└── dataset_convert/                 # 转换结果输出目录

```

## 安装依赖

```bash
pip install pyyaml
pip install Pillow    # 可选，用于获取图片尺寸 (未安装时自动回退到纯 Python 解析)
```

## 快速开始

### 1. 使用配置文件 (推荐)

编辑 `config.yaml`：

```yaml
format: yolo                                    # yolo | voc | coco | anylabeling
dataset_root: /path/to/your/dataset             # 数据集根目录
output_dir: null                                # 输出目录 (null = 自动在数据集目录下创建 labelstudio_output)
images_subdir: null                             # 图片子目录 (null = 自动查找)
labels_subdir: null                             # 标注子目录 (null = 自动查找)
annotation_json: null                           # COCO 标注 JSON 路径 (仅 COCO)
classes_file: null                              # YOLO 类别文件路径 (仅 YOLO)
```

运行：

```bash
python main.py
```

### 2. 使用命令行参数

```bash
# YOLO 格式
python main.py --format yolo --dataset-root ./my_yolo_dataset

# VOC 格式
python main.py --format voc --dataset-root ./my_voc_dataset

# COCO 格式 (需指定标注 JSON)
python main.py --format coco --dataset-root ./my_coco --annotation-json ./annotations.json

# AnyLabeling 格式
python main.py --format anylabeling --dataset-root ./my_anylabeling_dataset

# 指定配置文件
python main.py --config my_config.yaml

# 指定输出目录
python main.py --format yolo --dataset-root ./data --output ./output
```

### 命令行参数

| 参数                  | 缩写   | 说明                                                       |
| --------------------- | ------ | ---------------------------------------------------------- |
| `--config`          | `-c` | 配置文件路径 (默认:`config.yaml`)                        |
| `--format`          | `-f` | 数据集格式:`yolo` / `voc` / `coco` / `anylabeling` |
| `--dataset-root`    | `-d` | 数据集根目录                                               |
| `--output`          | `-o` | 输出目录                                                   |
| `--images-subdir`   |        | 图片子目录名                                               |
| `--labels-subdir`   |        | 标注子目录名                                               |
| `--annotation-json` |        | COCO 标注 JSON 路径 (仅 COCO)                              |
| `--classes-file`    |        | YOLO 类别文件路径 (仅 YOLO)                                |

> 命令行参数优先级高于配置文件。

## 数据集目录结构要求

### YOLO

```
dataset/
├── images/          # 图片
├── labels/          # 标注 .txt (每行: class_id cx cy w h, 归一化 0~1)
└── classes.txt      # 类别列表 (每行一个类别名)
```

### Pascal VOC

```
dataset/
├── JPEGImages/      # 图片 (或 images/)
└── Annotations/     # 标注 .xml (含 object/bndbox)
```

### COCO

```
dataset/
├── images/          # 图片
└── annotations/     # JSON 标注文件
    └── instances_train.json
```

### AnyLabeling

```
dataset/
├── images/          # 图片 (或根目录)
└── labels/          # AnyLabeling 导出的 JSON 标注 (或根目录)
```

AnyLabeling JSON 格式：

```json
{
  "name": "image.png",
  "objects": [
    { "label": "cat", "rectangle": [x, y, width, height] },
    { "label": "dog", "polygon": [[x1, y1], [x2, y2], ...] }
  ]
}
```

## 输出说明

转换后在输出目录生成两个文件：

- **`labelstudio_annotations.json`** — LabelStudio 预标注文件，包含所有图片的标注信息
- **`labelstudio_config.xml`** — LabelStudio 标注界面配置文件，定义类别和标注类型

### 输出示例

`labelstudio_annotations.json`:

```json
[
  {
    "data": { "image": "/data/local-files/?d=./images/sample.jpg" },
    "predictions": [
      {
        "result": [
          {
            "id": "box1",
            "type": "rectanglelabels",
            "from_name": "label",
            "to_name": "image",
            "value": {
              "x": 10.0, "y": 20.0,
              "width": 30.0, "height": 40.0,
              "rectanglelabels": ["cat"]
            }
          }
        ]
      }
    ]
  }
]
```

`labelstudio_config.xml`:

```xml
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="Airplane" background="green"/>
    <Label value="Car" background="blue"/>
  </RectangleLabels>
</View>
```

## 在 Label Studio 中导入

1. 创建新项目，在 **Labeling Interface** 中粘贴 `labelstudio_config.xml` 的内容
2. 导入图片：使用 **Local Storage** 方式，指向数据集的图片目录
3. 导入预标注：上传 `labelstudio_annotations.json`
