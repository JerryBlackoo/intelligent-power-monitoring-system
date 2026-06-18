from time import sleep, time

from edge_runtime.camera_reader import CameraReader
from edge_runtime.config import load_config
from edge_runtime.inference_engine import build_inference_engine
from edge_runtime.pipeline import InspectionPipeline
from edge_runtime.uploader import CloudUploader


def main() -> None:
    config = load_config()
    uploader = CloudUploader(config)
    pipeline = InspectionPipeline(
        config=config,
        camera=CameraReader(config),
        inference=build_inference_engine(config),
        uploader=uploader,
    )

    last_heartbeat = 0.0
    while True:
        now = time()
        if now - last_heartbeat >= config.heartbeat_interval_seconds:
            try:
                uploader.post_heartbeat()
                last_heartbeat = now
            except Exception as exc:
                print(f"heartbeat failed: {exc}")

        try:
            result = pipeline.run_once()
            print(f"inspection uploaded: {result['image_uri']}")
        except Exception as exc:
            print(f"inspection failed: {exc}")

        sleep(config.inspect_interval_seconds)


if __name__ == "__main__":
    main()
