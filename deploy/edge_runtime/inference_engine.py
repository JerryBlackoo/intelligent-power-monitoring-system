from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from edge_runtime.config import EdgeConfig
from edge_runtime.status_mapper import map_detection_status


class InferenceEngine:
    def infer(self, image_path: Path) -> List[Dict[str, Any]]:
        raise NotImplementedError


class MockInferenceEngine(InferenceEngine):
    def infer(self, image_path: Path) -> List[Dict[str, Any]]:
        detection = {
            "label": "red_indicator",
            "confidence": 0.91,
            "bbox": [120, 80, 60, 40],
            "description": "开发板端 mock：检测到红色告警指示灯",
        }
        detection["status"] = map_detection_status(detection["label"], detection["confidence"])
        return [detection]


class AclOmInferenceEngine(InferenceEngine):
    def __init__(self, config: EdgeConfig):
        self.config = config
        self.model_path = Path(config.model_path).expanduser().resolve()
        if not self.model_path.is_file():
            raise RuntimeError(f"OM model not found: {self.model_path}")
        try:
            import acl
            import cv2
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("ACL mode requires CANN acl, OpenCV and NumPy on the Atlas board") from exc

        self.acl = acl
        self.cv2 = cv2
        self.np = np
        self.device_id = config.acl_device_id
        self.model_id = None
        self.model_desc = None
        self.context = None
        self.model_width = 640
        self.model_height = 640
        self.input_dtype = np.dtype(np.float32)
        self.class_names = self._load_class_names()
        self._init_acl()
        self._load_model()

    def infer(self, image_path: Path) -> List[Dict[str, Any]]:
        image = self.cv2.imread(str(image_path), self.cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"failed to read image for inference: {image_path}")
        raw_h, raw_w = image.shape[:2]
        input_tensor = self._preprocess(image)
        output = self._execute(input_tensor)
        return self._postprocess(output, raw_w, raw_h)

    def close(self) -> None:
        if self.model_id is not None:
            self.acl.mdl.unload(self.model_id)
            self.model_id = None
        if self.model_desc is not None:
            self.acl.mdl.destroy_desc(self.model_desc)
            self.model_desc = None
        if self.context is not None:
            self.acl.rt.destroy_context(self.context)
            self.context = None
        try:
            self.acl.rt.reset_device(self.device_id)
            self.acl.finalize()
        except Exception:
            pass

    def _init_acl(self) -> None:
        ret = self.acl.init()
        if ret:
            print(f"[WARN] acl.init returned {ret}, continue to set device")
        ret = self.acl.rt.set_device(self.device_id)
        if ret:
            raise RuntimeError(f"acl.rt.set_device failed: {ret}")
        self.context, ret = self.acl.rt.create_context(self.device_id)
        if ret:
            raise RuntimeError(f"acl.rt.create_context failed: {ret}")

    def _load_model(self) -> None:
        self.model_id, ret = self.acl.mdl.load_from_file(str(self.model_path))
        if ret:
            raise RuntimeError(f"acl.mdl.load_from_file failed: {ret}")
        self.model_desc = self.acl.mdl.create_desc()
        ret = self.acl.mdl.get_desc(self.model_desc, self.model_id)
        if ret:
            raise RuntimeError(f"acl.mdl.get_desc failed: {ret}")

        dims = self._parse_nchw(self.acl.mdl.get_input_dims(self.model_desc, 0))
        if dims:
            _, _, self.model_height, self.model_width = dims
        input_size = self.acl.mdl.get_input_size_by_index(self.model_desc, 0)
        elems = 1 * 3 * self.model_height * self.model_width
        self.input_dtype = self.np.dtype(self.np.float16 if input_size == elems * 2 else self.np.float32)

    def _preprocess(self, image):
        resized = self.cv2.resize(image, (self.model_width, self.model_height))
        rgb = self.cv2.cvtColor(resized, self.cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(self.np.float32) / 255.0
        chw = self.np.transpose(normalized, (2, 0, 1))
        return self.np.ascontiguousarray(chw[None, ...], dtype=self.input_dtype)

    def _execute(self, input_tensor):
        acl = self.acl
        
        ret = acl.rt.set_context(self.context)
        if ret:
          raise RuntimeError(f"acl.rt.set_context failed: {ret}")
          
        input_dataset = acl.mdl.create_dataset()
        output_dataset = acl.mdl.create_dataset()
        input_buffer = None
        output_buffers = []
        try:
            input_size = acl.mdl.get_input_size_by_index(self.model_desc, 0)
            input_buffer, ret = acl.rt.malloc(input_size, self._mem_malloc_normal_policy())
            if ret:
                raise RuntimeError(f"acl.rt.malloc input failed: {ret}")

            input_blob = self._fit_input_blob(input_tensor, input_size)
            ret = acl.rt.memcpy(
                input_buffer,
                input_size,
                self._host_ptr(input_blob),
                input_size,
                self._acl_const("ACL_MEMCPY_HOST_TO_DEVICE", 1),
            )
            if ret:
                raise RuntimeError(f"H2D memcpy failed: {ret}")

            input_data = acl.create_data_buffer(input_buffer, input_size)
            _, ret = acl.mdl.add_dataset_buffer(input_dataset, input_data)
            if ret:
                raise RuntimeError(f"add input dataset buffer failed: {ret}")

            output_count = acl.mdl.get_num_outputs(self.model_desc)
            for idx in range(output_count):
                size = acl.mdl.get_output_size_by_index(self.model_desc, idx)
                buffer, ret = acl.rt.malloc(size, self._mem_malloc_normal_policy())
                if ret:
                    raise RuntimeError(f"acl.rt.malloc output failed: {ret}")
                output_buffers.append(buffer)
                output_data = acl.create_data_buffer(buffer, size)
                _, ret = acl.mdl.add_dataset_buffer(output_dataset, output_data)
                if ret:
                    raise RuntimeError(f"add output dataset buffer failed: {ret}")

            ret = acl.mdl.execute(self.model_id, input_dataset, output_dataset)
            if ret:
                raise RuntimeError(f"acl.mdl.execute failed: {ret}")

            outputs = []
            for idx, buffer in enumerate(output_buffers):
                size = acl.mdl.get_output_size_by_index(self.model_desc, idx)
                dtype, shape = self._output_dtype_shape(idx, size)
                host_buf = self.np.empty(size, dtype=self.np.uint8)
                ret = acl.rt.memcpy(
                    acl.util.numpy_to_ptr(host_buf),
                    size,
                    buffer,
                    size,
                    self._acl_const("ACL_MEMCPY_DEVICE_TO_HOST", 2),
                )
                if ret:
                    raise RuntimeError(f"D2H memcpy failed: {ret}")
                outputs.append(host_buf.view(dtype).reshape(shape).copy())
            return outputs[0] if len(outputs) == 1 else outputs
        finally:
            self._destroy_dataset(input_dataset, free_buffers=False)
            self._destroy_dataset(output_dataset, free_buffers=False)
            
            if input_buffer is not None:
              acl.rt.free(input_buffer)
            
            for buffer in output_buffers:
                acl.rt.free(buffer)
            

    def _postprocess(self, output, raw_w: int, raw_h: int) -> List[Dict[str, Any]]:
        np = self.np
        if isinstance(output, list):
            output = output[0]
        arr = np.asarray(output)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2:
            arr = arr.reshape(-1, arr.shape[-1])
        # YOLO output may be [C, N], e.g. [25, 18900] = 4 boxes + 21 classes
        # Convert it to [N, C] before postprocess.
        if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 128:
            arr = arr.T
        if arr.shape[1] < 5:
            return []

        boxes = arr[:, :4].astype(np.float32)
        raw_scores = arr[:, 4:].astype(np.float32)

        num_classes = len(self.class_names)

        if raw_scores.shape[1] == num_classes + 1:
            objectness = raw_scores[:, 0]
            class_scores = raw_scores[:, 1:]
            class_ids = np.argmax(class_scores, axis=1)
            confidences = objectness * np.max(class_scores, axis=1)
        elif raw_scores.shape[1] == num_classes:
            class_scores = raw_scores
            class_ids = np.argmax(class_scores, axis=1)
            confidences = np.max(class_scores, axis=1)
        elif raw_scores.shape[1] > num_classes:
            class_scores = raw_scores[:, -num_classes:]
            class_ids = np.argmax(class_scores, axis=1)
            confidences = np.max(class_scores, axis=1)
        else:
            class_ids = np.zeros(len(raw_scores), dtype=np.int32)
            confidences = raw_scores[:, 0]

        mask = confidences >= self.config.confidence_threshold
        boxes = boxes[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]
        if len(boxes) == 0:
            return []

        x, y, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1 = x - w / 2
        y1 = y - h / 2
        x2 = x + w / 2
        y2 = y + h / 2
        keep = self._nms(np.column_stack([x1, y1, x2, y2]), confidences, self.config.iou_threshold)

        detections = []
        for idx in keep:
            cid = int(class_ids[idx])
            label = self.class_names[cid] if cid < len(self.class_names) else f"class_{cid}"
            ox1 = max(0, int(x1[idx] / self.model_width * raw_w))
            oy1 = max(0, int(y1[idx] / self.model_height * raw_h))
            ox2 = min(raw_w, int(x2[idx] / self.model_width * raw_w))
            oy2 = min(raw_h, int(y2[idx] / self.model_height * raw_h))
            confidence = float(confidences[idx])
            detections.append(
                {
                    "label": label,
                    "confidence": confidence,
                    "bbox": [ox1, oy1, max(0, ox2 - ox1), max(0, oy2 - oy1)],
                    "status": map_detection_status(label, confidence),
                    "description": f"检测到 {label}",
                }
            )
        return detections

    def _nms(self, boxes, scores, iou_threshold: float) -> List[int]:
        np = self.np
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / np.maximum(areas[i] + areas[order[1:]] - inter, 1e-6)
            order = order[np.where(iou <= iou_threshold)[0] + 1]
        return keep

    def _fit_input_blob(self, input_tensor, input_size: int):
        arr = self.np.ascontiguousarray(input_tensor, dtype=self.input_dtype)
        if arr.nbytes == input_size:
            return arr
        if arr.nbytes > input_size:
            raise RuntimeError(f"input tensor bytes {arr.nbytes} exceeds OM input buffer {input_size}")
        total = input_size // arr.dtype.itemsize
        blob = self.np.zeros(total, dtype=arr.dtype)
        flat = arr.ravel()
        blob[: flat.size] = flat
        return blob

    def _output_dtype_shape(self, index: int, size: int):
        np = self.np
        shape = self._shape_tuple(self.acl.mdl.get_output_dims(self.model_desc, index))
        dtype = np.dtype(np.float32)
        if shape is not None and int(np.prod(shape)) * dtype.itemsize == size:
            return dtype, shape
        if shape is not None and int(np.prod(shape)) * np.dtype(np.float16).itemsize == size:
            return np.dtype(np.float16), shape
        if size % 4 == 0:
            return np.dtype(np.float32), (size // 4,)
        return np.dtype(np.float16), (size // 2,)

    def _destroy_dataset(self, dataset, free_buffers: bool) -> None:
        if dataset is None:
            return
        count = self.acl.mdl.get_dataset_num_buffers(dataset)
        for idx in range(count):
            data_buf = self.acl.mdl.get_dataset_buffer(dataset, idx)
            if data_buf:
                if free_buffers:
                    data = self.acl.get_data_buffer_addr(data_buf)
                    self.acl.rt.free(data)
                self.acl.destroy_data_buffer(data_buf)
        self.acl.mdl.destroy_dataset(dataset)

    def _host_ptr(self, arr):
        arr = self.np.ascontiguousarray(arr)
        return self.acl.util.numpy_to_ptr(arr)

    def _acl_const(self, name: str, fallback: int):
        for obj in (self.acl, getattr(self.acl, "rt", None)):
            if obj is not None and hasattr(obj, name):
                return getattr(obj, name)
        try:
            import constants

            return getattr(constants, name, fallback)
        except ImportError:
            return fallback

    def _mem_malloc_normal_policy(self):
        return self._acl_const("ACL_MEM_MALLOC_HUGE_FIRST", 0)

    def _parse_nchw(self, raw) -> Optional[Tuple[int, int, int, int]]:
        shape = self._shape_tuple(raw)
        if shape and len(shape) >= 4:
            return tuple(int(x) for x in shape[:4])
        return None

    def _shape_tuple(self, raw):
        if raw is None:
            return None
        if isinstance(raw, dict) and "dims" in raw:
            return self._shape_tuple(raw["dims"])
        if isinstance(raw, (list, tuple)) and raw:
            if isinstance(raw[0], dict):
                return self._shape_tuple(raw[0])
            if all(isinstance(x, (int, self.np.integer)) for x in raw):
                return tuple(int(x) for x in raw)
            if isinstance(raw[0], (list, tuple)):
                return self._shape_tuple(raw[0])
        return None

    def _load_class_names(self) -> List[str]:
        names_path = Path(self.config.class_names_path).expanduser().resolve()
        if names_path.is_file():
            return [line.strip() for line in names_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return ["insulator_normal", "insulator_defect", "foreign_object", "bird_nest"]


def build_inference_engine(config: EdgeConfig) -> InferenceEngine:
    if config.inference_mode == "acl":
        try:
            return AclOmInferenceEngine(config)
        except Exception as exc:
            if not config.fallback_to_mock:
                raise
            print(f"ACL inference init failed, fallback to mock: {exc}")
    return MockInferenceEngine()
