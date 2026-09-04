import json
import os

import cv2
import numpy as np
import rclpy
import message_filters

from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, PoseStamped
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException
from ultralytics import YOLO

# Necessário para registrar conversões de mensagens no TF2.
import tf2_geometry_msgs  # noqa: F401


class RAVVision3D(Node):
    def __init__(self):
        super().__init__("rav_vision_3d")

        # ----------------------------
        # Parâmetros do modelo YOLO
        # ----------------------------
        self.declare_parameter("model_path", "")
        self.declare_parameter("imgsz", 512)
        self.declare_parameter("conf", 0.25)
        self.declare_parameter("device", "cpu")

        # ----------------------------
        # Tópicos da câmera
        # Ajuste depois de verificar ros2 topic list
        # ----------------------------
        self.declare_parameter("color_topic", "/camera/color/image_raw")
        self.declare_parameter(
            "depth_topic",
            "/camera/depth/image_raw"
        )
        self.declare_parameter(
            "camera_info_topic",
            "/camera/color/camera_info"
        )

        # ----------------------------
        # Parâmetros de profundidade
        # ----------------------------
        self.declare_parameter("depth_unit_scale", 0.001)
        self.declare_parameter("min_depth_m", 0.15)
        self.declare_parameter("max_depth_m", 1.50)
        self.declare_parameter("roi_ratio", 0.50)
        self.declare_parameter("min_valid_depth_pixels", 30)

        # ----------------------------
        # TF e seleção do alvo
        # ----------------------------
        self.declare_parameter("target_frame", "base_link")
        self.declare_parameter("target_class", "")
        self.declare_parameter("visualize", True)

        self.model_path = self.get_parameter("model_path").value
        self.imgsz = int(self.get_parameter("imgsz").value)
        self.conf = float(self.get_parameter("conf").value)
        self.device = str(self.get_parameter("device").value)

        self.color_topic = str(
            self.get_parameter("color_topic").value
        )
        self.depth_topic = str(
            self.get_parameter("depth_topic").value
        )
        self.camera_info_topic = str(
            self.get_parameter("camera_info_topic").value
        )

        self.depth_unit_scale = float(
            self.get_parameter("depth_unit_scale").value
        )
        self.min_depth_m = float(
            self.get_parameter("min_depth_m").value
        )
        self.max_depth_m = float(
            self.get_parameter("max_depth_m").value
        )
        self.roi_ratio = float(
            self.get_parameter("roi_ratio").value
        )
        self.min_valid_depth_pixels = int(
            self.get_parameter("min_valid_depth_pixels").value
        )

        self.target_frame = str(
            self.get_parameter("target_frame").value
        )
        self.target_class = str(
            self.get_parameter("target_class").value
        )
        self.visualize = bool(
            self.get_parameter("visualize").value
        )

        if not self.model_path:
            raise ValueError(
                "Informe model_path com o caminho do best_50epochs.pt"
            )

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Modelo não encontrado: {self.model_path}"
            )

        self.get_logger().info(
            f"Carregando modelo YOLO: {self.model_path}"
        )
        self.model = YOLO(self.model_path)

        self.bridge = CvBridge()

        # Intrínsecos da câmera RGB.
        self.fx = None
        self.fy = None
        self.cx = None
        self.cy = None

        # TF: câmera -> base_link.
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(
            self.tf_buffer,
            self
        )

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # CameraInfo normalmente é estático; não precisa sincronizar.
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            self.camera_info_topic,
            self.camera_info_callback,
            sensor_qos
        )

        # RGB e profundidade precisam chegar com timestamps próximos.
        self.color_sub = message_filters.Subscriber(
            self,
            Image,
            self.color_topic,
            qos_profile=sensor_qos
        )

        self.depth_sub = message_filters.Subscriber(
            self,
            Image,
            self.depth_topic,
            qos_profile=sensor_qos
        )

        self.sync = message_filters.ApproximateTimeSynchronizer(
            [self.color_sub, self.depth_sub],
            queue_size=8,
            slop=0.08
        )

        self.sync.registerCallback(self.synced_callback)

        self.detections_pub = self.create_publisher(
            String,
            "/rav_vision/detections_3d",
            10
        )

        self.target_pose_pub = self.create_publisher(
            PoseStamped,
            "/rav_vision/target_pose",
            10
        )

        self.get_logger().info("RAV Vision 3D iniciado.")
        self.get_logger().info(f"RGB: {self.color_topic}")
        self.get_logger().info(f"Depth: {self.depth_topic}")
        self.get_logger().info(f"CameraInfo: {self.camera_info_topic}")

    def camera_info_callback(self, msg: CameraInfo):
        """
        Salva os intrínsecos da câmera RGB.

        K = [fx, 0, cx,
             0, fy, cy,
             0, 0, 1]
        """

        if msg.k[0] <= 0.0 or msg.k[4] <= 0.0:
            self.get_logger().warn(
                "CameraInfo recebido, mas intrínsecos inválidos."
            )
            return

        self.fx = float(msg.k[0])
        self.fy = float(msg.k[4])
        self.cx = float(msg.k[2])
        self.cy = float(msg.k[5])

    def synced_callback(self, color_msg: Image, depth_msg: Image):
        """
        Executa YOLO no RGB e obtém profundidade correspondente
        no mapa de depth alinhado ao RGB.
        """

        if None in (self.fx, self.fy, self.cx, self.cy):
            self.get_logger().warn(
                "Aguardando CameraInfo com os intrínsecos da câmera."
            )
            return

        try:
            color_bgr = self.bridge.imgmsg_to_cv2(
                color_msg,
                desired_encoding="bgr8"
            )

            depth_raw = self.bridge.imgmsg_to_cv2(
                depth_msg,
                desired_encoding="passthrough"
            )

        except Exception as exc:
            self.get_logger().error(
                f"Erro ao converter imagens ROS: {exc}"
            )
            return

        if color_bgr.shape[:2] != depth_raw.shape[:2]:
            self.get_logger().warn(
                "RGB e depth possuem resoluções diferentes. "
                "Ative depth_registration na Orbbec ou utilize "
                "um tópico de profundidade já registrado no RGB."
            )
            return

        depth_m = self.depth_to_meters(depth_raw)

        try:
            results = self.model.predict(
                source=color_bgr,
                imgsz=self.imgsz,
                conf=self.conf,
                device=self.device,
                verbose=False
            )
        except Exception as exc:
            self.get_logger().error(
                f"Erro durante inferência YOLO: {exc}"
            )
            return

        result = results[0]
        detections_3d = []
        valid_targets = []

        for box in result.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            class_name = str(self.model.names[class_id])

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            depth_result = self.get_robust_depth(
                depth_m,
                x1,
                y1,
                x2,
                y2
            )

            if depth_result is None:
                continue

            z_m, u, v, valid_depth_pixels = depth_result

            # Projeção inversa pinhole:
            # X = (u - cx) * Z / fx
            # Y = (v - cy) * Z / fy
            # Z = profundidade
            x_m = ((u - self.cx) * z_m) / self.fx
            y_m = ((v - self.cy) * z_m) / self.fy

            point_camera = PointStamped()
            point_camera.header = color_msg.header
            point_camera.point.x = float(x_m)
            point_camera.point.y = float(y_m)
            point_camera.point.z = float(z_m)

            point_target = self.transform_to_target_frame(
                point_camera
            )

            detection = {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "bbox": {
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2)
                },
                "pixel_center": {
                    "u": round(u, 2),
                    "v": round(v, 2)
                },
                "depth_m": round(z_m, 4),
                "valid_depth_pixels": valid_depth_pixels,
                "position_camera_m": {
                    "x": round(x_m, 4),
                    "y": round(y_m, 4),
                    "z": round(z_m, 4)
                }
            }

            if point_target is not None:
                detection["target_frame"] = point_target.header.frame_id
                detection["position_target_m"] = {
                    "x": round(point_target.point.x, 4),
                    "y": round(point_target.point.y, 4),
                    "z": round(point_target.point.z, 4)
                }

                if (
                    not self.target_class
                    or class_name == self.target_class
                ):
                    valid_targets.append(
                        (confidence, point_target, detection)
                    )

            detections_3d.append(detection)

        self.publish_detections(
            color_msg,
            detections_3d
        )

        self.publish_best_target(valid_targets)

        if self.visualize:
            self.show_visualization(
                color_bgr,
                result,
                detections_3d
            )

    def depth_to_meters(self, depth_raw: np.ndarray) -> np.ndarray:
        """
        Converte a imagem de profundidade para metros.

        Em geral:
        - uint16 / 16UC1: milímetros
        - float32 / 32FC1: metros
        """

        if np.issubdtype(depth_raw.dtype, np.integer):
            return depth_raw.astype(np.float32) * self.depth_unit_scale

        if np.issubdtype(depth_raw.dtype, np.floating):
            return depth_raw.astype(np.float32)

        raise TypeError(
            f"Formato de profundidade não suportado: {depth_raw.dtype}"
        )

    def get_robust_depth(
        self,
        depth_m: np.ndarray,
        x1: float,
        y1: float,
        x2: float,
        y2: float
    ):
        """
        Obtém a profundidade usando a mediana de uma região central
        da bounding box.

        Evita usar somente o pixel central, que pode conter ruído,
        falha de profundidade ou fundo.
        """

        height, width = depth_m.shape[:2]

        x1 = int(np.clip(x1, 0, width - 1))
        y1 = int(np.clip(y1, 0, height - 1))
        x2 = int(np.clip(x2, 0, width - 1))
        y2 = int(np.clip(y2, 0, height - 1))

        if x2 <= x1 or y2 <= y1:
            return None

        u = int((x1 + x2) / 2)
        v = int((y1 + y2) / 2)

        box_width = x2 - x1
        box_height = y2 - y1

        half_width = max(
            2,
            int((box_width * self.roi_ratio) / 2)
        )

        half_height = max(
            2,
            int((box_height * self.roi_ratio) / 2)
        )

        roi_x1 = max(0, u - half_width)
        roi_x2 = min(width, u + half_width)

        roi_y1 = max(0, v - half_height)
        roi_y2 = min(height, v + half_height)

        roi = depth_m[roi_y1:roi_y2, roi_x1:roi_x2]

        valid = roi[np.isfinite(roi)]

        valid = valid[
            (valid >= self.min_depth_m)
            & (valid <= self.max_depth_m)
        ]

        if valid.size < self.min_valid_depth_pixels:
            return None

        median_depth = float(np.median(valid))

        # Remove outliers usando Median Absolute Deviation.
        mad = float(np.median(np.abs(valid - median_depth)))

        if mad > 0.0:
            threshold = max(0.01, 3.0 * mad)

            inliers = valid[
                np.abs(valid - median_depth) <= threshold
            ]

            if inliers.size >= self.min_valid_depth_pixels:
                median_depth = float(np.median(inliers))

        return median_depth, u, v, int(valid.size)

    def transform_to_target_frame(
        self,
        point_camera: PointStamped
    ):
        """
        Converte o ponto do frame óptico da câmera para base_link,
        ou para qualquer outro frame definido em target_frame.
        """

        if not self.target_frame:
            return point_camera

        if point_camera.header.frame_id == self.target_frame:
            return point_camera

        try:
            # O braço já está estabilizado em ready quando a detecção
            # acontece. Usamos a transformação mais recente disponível
            # para evitar extrapolação temporal entre câmera e joint_states.
            transform = self.tf_buffer.lookup_transform(
                self.target_frame,
                point_camera.header.frame_id,
                Time(),
                timeout=Duration(seconds=0.20)
            )

            point_target = tf2_geometry_msgs.do_transform_point(
                point_camera,
                transform
            )

            # Preserva o timestamp original da detecção.
            point_target.header.stamp = point_camera.header.stamp
            point_target.header.frame_id = self.target_frame

            return point_target

        except TransformException as exc:
            self.get_logger().warn(
                f"TF indisponível para "
                f"{point_camera.header.frame_id} -> "
                f"{self.target_frame}: {exc}"
            )
            return None

    def publish_detections(
        self,
        color_msg: Image,
        detections_3d: list
    ):
        msg = String()

        msg.data = json.dumps({
            "frame_id": color_msg.header.frame_id,
            "stamp_sec": color_msg.header.stamp.sec,
            "stamp_nanosec": color_msg.header.stamp.nanosec,
            "detections": detections_3d
        })

        self.detections_pub.publish(msg)

    def publish_best_target(self, valid_targets: list):
        """
        Publica o alvo de maior confiança no tópico usado
        posteriormente pelo planejador do manipulador.
        """

        if not valid_targets:
            return

        _, point_target, _ = max(
            valid_targets,
            key=lambda item: item[0]
        )

        pose_msg = PoseStamped()
        pose_msg.header = point_target.header

        pose_msg.pose.position.x = point_target.point.x
        pose_msg.pose.position.y = point_target.point.y
        pose_msg.pose.position.z = point_target.point.z

        # Ainda não é orientação de pega.
        # Quaternion identidade apenas mantém a mensagem válida.
        pose_msg.pose.orientation.x = 0.0
        pose_msg.pose.orientation.y = 0.0
        pose_msg.pose.orientation.z = 0.0
        pose_msg.pose.orientation.w = 1.0

        self.target_pose_pub.publish(pose_msg)

    def show_visualization(
        self,
        color_bgr: np.ndarray,
        result,
        detections_3d: list
    ):
        frame = result.plot()

        for detection in detections_3d:
            x1 = int(detection["bbox"]["x1"])
            y1 = int(detection["bbox"]["y1"])

            pos = detection.get("position_target_m")
            frame_name = detection.get("target_frame", "camera")

            if pos is not None:
                text = (
                    f'{detection["class_name"]} | '
                    f'[{pos["x"]:.2f}, '
                    f'{pos["y"]:.2f}, '
                    f'{pos["z"]:.2f}] m '
                    f'({frame_name})'
                )
            else:
                pos_camera = detection["position_camera_m"]

                text = (
                    f'{detection["class_name"]} | '
                    f'[{pos_camera["x"]:.2f}, '
                    f'{pos_camera["y"]:.2f}, '
                    f'{pos_camera["z"]:.2f}] m '
                    f'(camera)'
                )

            cv2.putText(
                frame,
                text,
                (x1, max(25, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA
            )

        cv2.imshow("RAV Vision - YOLO26 3D", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            rclpy.shutdown()

    def destroy_node(self):
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = RAVVision3D()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()