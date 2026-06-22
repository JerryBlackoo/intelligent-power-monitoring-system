# 电力智能巡检 YOLOv8 训练说明

本目录保存“基于 Atlas 200I DK 开发板的电力智能巡检”项目的模型训练代码、最终权重和验证结果。模型采用 **Ultralytics YOLOv8s**（small）目标检测网络训练，兼顾识别精度和 Atlas 端侧部署的模型规模。

## 两个模型的用途

| 模型 | 作用 | 输入/输出 |
| --- | --- | --- |
| 模型一：电力设备统一检测 | 在摄像头画面中定位并识别主要电力设备。类别为：绝缘子、空气开关、配电柜、光伏板。 | 输入整帧图像，输出设备类别、边界框和置信度。 |
| 模型二：设备状态与缺陷检测 | 对设备及其组件进行细粒度状态/故障识别。包含绝缘子破损/污闪、空气开关、配电柜组件与开关状态、光伏板污渍/损坏/积雪等类别。 | 输入图像（也可接收模型一裁剪出的设备区域），输出状态或缺陷类别、边界框和置信度。 |

## 数据集来源与处理

所有原始数据集均由项目组在本地收集，原始目录为 `E:\Atlas\绝缘子检测数据集`。其中配电柜空气开关数据集原为 COCO 标注格式，已转换为 YOLO 格式；其余数据集为 YOLOv8 格式。

| 数据集 | 原始类别/内容 | 用途 |
| --- | --- | --- |
| 数据集1-绝缘子 | `broken disc`、`insulator`、`pollution-flashover`；来源为 GitHub 开源绝缘子检测数据集 | 模型一绝缘子检测、模型二绝缘子状态/缺陷检测 |
| 数据集2-配电柜空气开关 | `Electrical-Panel`、`Circuit breaker`、`rcd`；COCO 格式 | 模型一空气开关/配电柜检测、模型二空气开关识别 |
| 数据集3-配电柜 | 配电柜、旋钮、闸门、指示灯、指针及开关状态等 10 类 | 模型一配电柜检测、模型二柜体组件与状态检测 |
| 数据集4-光伏板 | 鸟粪、缺陷、灰尘、电气损伤、正常、物理损伤、积雪等 7 类 | 模型一光伏板检测、模型二光伏板缺陷检测 |

数据准备后，模型一共使用 4 个统一设备类别；模型二共使用 21 个细粒度状态/缺陷类别。

## 训练配置

- 基础网络：`yolov8s.pt`（预训练权重）
- 训练轮数：100 epochs
- 随机种子：20260622
- 模型一图像尺寸 / 批量大小：640 / 16
- 模型二图像尺寸 / 批量大小：960 / 8
- 优化器：Ultralytics 自动选择（`optimizer=auto`）
- 学习率策略：余弦学习率（`cos_lr=True`）

## 训练命令

安装依赖：

```powershell
pip install ultralytics
```

脚本原始运行目录为项目工作区根目录。若在其他电脑复现，请先将 `train/code/*.py` 中的 `ROOT` 路径改为本机工作区路径，并准备相同的数据集目录结构。

```powershell
# 1. 将 COCO 格式的空气开关数据集转换为 YOLO 格式
python train/code/coco_to_yolo.py

# 2. 合并四个数据集并生成两个模型所需的数据集
python train/code/prepare_power_datasets.py

# 3. 依次训练模型一和模型二
python train/code/train_yolov8.py
```

## 验证结果

以下为对应 `best.pt` 最佳权重在验证集上的指标。

| 模型 | 最佳轮次 | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 模型一：电力设备统一检测 | 86 | 0.8130 | 0.8301 | 0.8289 | 0.7228 |
| 模型二：设备状态与缺陷检测 | 98 | 0.7875 | 0.7284 | 0.7411 | 0.5489 |

各模型完整的验证材料在 `validation_results/` 中，包括：

- `results.csv`：逐 epoch 的损失和指标；
- `results.png`：训练与验证曲线；
- `Box*_curve.png`：P、R、F1 和 PR 曲线；
- `confusion_matrix*.png`：混淆矩阵；
- `val_batch*_labels.jpg` 与 `val_batch*_pred.jpg`：验证集标注和预测效果对比。

## 最终模型文件

| 文件 | 说明 |
| --- | --- |
| `models/device_detect_best.pt` | 模型一 PyTorch 权重，用于继续训练或本地 YOLO 推理。 |
| `models/device_detect_best.onnx` | 模型一 ONNX 文件，供 Atlas 200I DK 使用 ATC 转换为 `.om` 模型。 |
| `models/state_defect_best.pt` | 模型二 PyTorch 权重，用于继续训练或本地 YOLO 推理。 |
| `models/state_defect_best.onnx` | 模型二 ONNX 文件，供 Atlas 200I DK 使用 ATC 转换为 `.om` 模型。 |

部署到 Atlas 200I DK 时，应优先使用 ONNX 文件，并在 CANN/ATC 环境中转换为 Ascend OM 格式；转换所需的输入尺寸分别为模型一 640×640、模型二 960×960。
