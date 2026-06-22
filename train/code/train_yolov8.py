"""Train the two prepared YOLOv8 models on the local RTX GPU."""

from pathlib import Path
from ultralytics import YOLO


ROOT = Path(r"C:\Users\Lenovo\Documents\Codex\2026-06-22\9-atlas-200i-dk-1-1")
DATASETS = ROOT / "outputs" / "training_datasets"
RUNS = ROOT / "outputs" / "yolov8_runs"


def train(name: str, data_file: Path, image_size: int, epochs: int, batch: int) -> None:
    model = YOLO("yolov8s.pt")
    model.train(
        data=str(data_file),
        epochs=epochs,
        imgsz=image_size,
        batch=batch,
        device=0,
        workers=4,
        project=str(RUNS),
        name=name,
        exist_ok=True,
        patience=30,
        pretrained=True,
        seed=20260622,
        optimizer="auto",
        # Avoid the optional online AMP verification download; CUDA AMP itself remains enabled by PyTorch.
        amp=False,
        cos_lr=True,
        plots=True,
    )


if __name__ == "__main__":
    # Start with the equipment locator. The state/defect model runs immediately after it.
    train("model_1_equipment", DATASETS / "model_1_equipment" / "data.yaml", 640, 100, 16)
    train("model_2_state_defect", DATASETS / "model_2_state_defect" / "data.yaml", 960, 100, 8)
