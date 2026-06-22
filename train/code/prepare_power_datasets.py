"""Build two YOLOv8 datasets for the power-inspection cascade.

Model 1 locates four equipment types.  Model 2 retains the available
fine-grained defect/state annotations, with source-specific class prefixes.
"""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(r"E:\Atlas\绝缘子检测数据集")
CONVERTED_SWITCH = Path(r"C:\Users\Lenovo\Documents\Codex\2026-06-22\9-atlas-200i-dk-1-1\outputs\air_switch_yolov8")
OUTPUT = Path(r"C:\Users\Lenovo\Documents\Codex\2026-06-22\9-atlas-200i-dk-1-1\outputs\training_datasets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


SOURCES = {
    "insulator": ROOT / "数据集1-绝缘子",
    "switch": CONVERTED_SWITCH,
    "cabinet": ROOT / "数据集3-配电柜",
    "solar": ROOT / "数据集4-光伏板",
}

MODEL_1_NAMES = ["insulator", "air_switch", "distribution_cabinet", "photovoltaic_panel"]
MODEL_1_MAP = {
    "insulator": {1: 0},
    "switch": {0: 2, 1: 1, 2: 1},
    "cabinet": {0: 2, 1: 2},
    "solar": {0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3},
}

MODEL_2_NAMES = [
    "insulator_broken_disc", "insulator_pollution_flashover",
    "switch_circuit_breaker", "switch_rcd",
    "cabinet_guizi_1", "cabinet_guizi_2", "cabinet_xuanniu_1", "cabinet_xuanniu_2",
    "cabinet_zhamen_1_off", "cabinet_zhamen_1_on", "cabinet_zhishideng_1_off",
    "cabinet_zhishideng_1_on", "cabinet_zhishideng_2_on", "cabinet_zhizhen_1",
    "pv_bird_drop", "pv_defective", "pv_dusty", "pv_electrical_damage",
    "pv_non_defective", "pv_physical_damage", "pv_snow",
]
MODEL_2_MAP = {
    "insulator": {0: 0, 2: 1},
    "switch": {1: 2, 2: 3},
    "cabinet": {index: index + 4 for index in range(10)},
    "solar": {index: index + 14 for index in range(7)},
}


def parse_labels(path: Path, mapping: dict[int, int]) -> list[str]:
    if not path.exists():
        return []
    converted = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        original_class = int(float(parts[0]))
        if original_class in mapping:
            converted.append(" ".join([str(mapping[original_class]), *parts[1:]]))
    return converted


def write_yaml(dataset_dir: Path, names: list[str]) -> None:
    content = [
        f"path: {dataset_dir.resolve().as_posix()}", "train: train/images", "val: valid/images", "test: test/images", "",
        f"nc: {len(names)}", "names:",
    ]
    content.extend(f"  {index}: {name}" for index, name in enumerate(names))
    (dataset_dir / "data.yaml").write_text("\n".join(content) + "\n", encoding="utf-8")


def build_dataset(name: str, class_names: list[str], class_maps: dict[str, dict[int, int]]) -> None:
    target = OUTPUT / name
    if target.exists():
        shutil.rmtree(target)
    stats = {split: {"images": 0, "boxes": 0} for split in ("train", "valid", "test")}
    for split in stats:
        (target / split / "images").mkdir(parents=True)
        (target / split / "labels").mkdir(parents=True)

    for source_name, source_root in SOURCES.items():
        for split in stats:
            source_images = source_root / split / "images"
            source_labels = source_root / split / "labels"
            if not source_images.exists():
                continue
            for image in source_images.iterdir():
                if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                labels = parse_labels(source_labels / f"{image.stem}.txt", class_maps[source_name])
                if not labels:
                    continue
                destination_stem = f"{source_name}__{image.stem}"
                shutil.copy2(image, target / split / "images" / f"{destination_stem}{image.suffix.lower()}")
                (target / split / "labels" / f"{destination_stem}.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")
                stats[split]["images"] += 1
                stats[split]["boxes"] += len(labels)
    write_yaml(target, class_names)
    readme = [f"{name} generated from the four provided datasets.", ""]
    readme.extend(f"{split}: {value['images']} images, {value['boxes']} boxes" for split, value in stats.items())
    (target / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(name, stats)


def main() -> None:
    build_dataset("model_1_equipment", MODEL_1_NAMES, MODEL_1_MAP)
    build_dataset("model_2_state_defect", MODEL_2_NAMES, MODEL_2_MAP)


if __name__ == "__main__":
    main()
