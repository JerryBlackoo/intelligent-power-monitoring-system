"""Convert one COCO detection dataset into a deterministic YOLOv8 layout."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260622)
    args = parser.parse_args()

    annotation_path = args.source / "_annotations.coco.json"
    with annotation_path.open(encoding="utf-8") as f:
        coco = json.load(f)

    categories = sorted(coco["categories"], key=lambda item: item["id"])
    category_to_index = {category["id"]: index for index, category in enumerate(categories)}
    annotations_by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in coco["annotations"]:
        if annotation.get("iscrowd", 0) == 0 and annotation["bbox"][2] > 0 and annotation["bbox"][3] > 0:
            annotations_by_image[annotation["image_id"]].append(annotation)

    images = [image for image in coco["images"] if (args.source / image["file_name"]).suffix.lower() in IMAGE_EXTENSIONS]
    images.sort(key=lambda image: image["file_name"])
    random.Random(args.seed).shuffle(images)

    count = len(images)
    train_end = round(count * 0.8)
    valid_end = train_end + round(count * 0.1)
    splits = {
        "train": images[:train_end],
        "valid": images[train_end:valid_end],
        "test": images[valid_end:],
    }

    if args.output.exists():
        shutil.rmtree(args.output)
    for split in splits:
        (args.output / split / "images").mkdir(parents=True)
        (args.output / split / "labels").mkdir(parents=True)

    written = 0
    for split, records in splits.items():
        for image in records:
            source_image = args.source / image["file_name"]
            destination_image = args.output / split / "images" / source_image.name
            shutil.copy2(source_image, destination_image)
            label_path = args.output / split / "labels" / f"{source_image.stem}.txt"
            width, height = image["width"], image["height"]
            lines = []
            for annotation in annotations_by_image[image["id"]]:
                x, y, box_width, box_height = annotation["bbox"]
                x1, y1 = max(0, x), max(0, y)
                x2, y2 = min(width, x + box_width), min(height, y + box_height)
                if x2 <= x1 or y2 <= y1:
                    continue
                x_center = ((x1 + x2) / 2) / width
                y_center = ((y1 + y2) / 2) / height
                normalized_width = (x2 - x1) / width
                normalized_height = (y2 - y1) / height
                cls = category_to_index[annotation["category_id"]]
                lines.append(f"{cls} {x_center:.6f} {y_center:.6f} {normalized_width:.6f} {normalized_height:.6f}")
                written += 1
            label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    names = [category["name"] for category in categories]
    yaml_lines = [
        "path: .",
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        f"nc: {len(names)}",
        "names:",
    ]
    yaml_lines.extend(f"  {index}: {name}" for index, name in enumerate(names))
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "README.txt").write_text(
        "Converted from COCO annotations with coco_to_yolo.py.\n"
        f"Images: train={len(splits['train'])}, valid={len(splits['valid'])}, test={len(splits['test'])}.\n"
        f"YOLO bounding boxes: {written}.\n"
        f"Classes: {', '.join(names)}.\n",
        encoding="utf-8",
    )
    print(f"Converted {count} images and {written} boxes to {args.output}")
    print("Split:", ", ".join(f"{name}={len(records)}" for name, records in splits.items()))
    print("Classes:", names)


if __name__ == "__main__":
    main()
