from typing import Any, Dict
from time import sleep, time

from edge_runtime.camera_reader import CameraReader
from edge_runtime.config import load_config
from edge_runtime.inference_engine import build_inference_engine
from edge_runtime.pipeline import InspectionPipeline
from edge_runtime.uploader import CloudUploader


COMMAND_POLL_INTERVAL_SECONDS = 3.0
CONFIG_SYNC_INTERVAL_SECONDS = 60.0


def handle_command(command: Dict[str, Any], pipeline: InspectionPipeline, uploader: CloudUploader) -> None:
    command_id = command["command_id"]
    command_type = command.get("command_type")
    device_id = command.get("device_id")

    try:
        if command_type != "start_inspection":
            uploader.ack_command(command_id, "failed", error_message=f"unsupported command: {command_type}")
            return

        result = pipeline.run_once(device_id=device_id)
        uploader.ack_command(command_id, "success", result={
            "captured_at": result["captured_at"],
            "image_uri": result["image_uri"],
            "cloud_result": result["cloud_result"],
        })
        print(f"command {command_id} completed: {result['image_uri']}")
    except Exception as exc:
        try:
            uploader.ack_command(command_id, "failed", error_message=str(exc))
        except Exception as ack_exc:
            print(f"command ack failed: {ack_exc}")
        print(f"command {command_id} failed: {exc}")


def poll_commands(pipeline: InspectionPipeline, uploader: CloudUploader) -> None:
    commands = uploader.fetch_commands()
    for command in commands:
        handle_command(command, pipeline, uploader)


def main() -> None:
    config = load_config()
    uploader = CloudUploader(config)
    pipeline = InspectionPipeline(
        config=config,
        camera=CameraReader(config),
        inference=build_inference_engine(config),
        uploader=uploader,
    )

    # P4: sync model version on startup
    pipeline.sync_deployment_config()

    last_heartbeat = 0.0
    last_inspection = 0.0
    last_command_poll = 0.0
    last_config_sync = time()
    while True:
        now = time()
        if now - last_heartbeat >= config.heartbeat_interval_seconds:
            try:
                uploader.post_heartbeat()
                last_heartbeat = now
            except Exception as exc:
                print(f"heartbeat failed: {exc}")

        if now - last_command_poll >= COMMAND_POLL_INTERVAL_SECONDS:
            try:
                poll_commands(pipeline, uploader)
                last_command_poll = now
            except Exception as exc:
                print(f"command poll failed: {exc}")

        # P4: periodic config sync
        if now - last_config_sync >= CONFIG_SYNC_INTERVAL_SECONDS:
            try:
                pipeline.sync_deployment_config()
                last_config_sync = now
            except Exception as exc:
                print(f"periodic config sync failed: {exc}")

        if now - last_inspection >= config.inspect_interval_seconds:
            try:
                result = pipeline.run_once()
                last_inspection = now
                print(f"inspection uploaded: {result['image_uri']}")
            except Exception as exc:
                print(f"inspection failed: {exc}")

        sleep(1.0)


if __name__ == "__main__":
    main()
