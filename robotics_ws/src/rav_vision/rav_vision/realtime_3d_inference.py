import json
import os
import threading
import time

import cv2
import numpy as np

import rclpy
import message_filters

from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, PoseStamped
from rcl_interfaces.msg import SetParametersResult
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
        self.declare_parameter("conf", 0.75)
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

        # Remendo rapido: o cy que o astra_camera_node publica no
        # camera_info (172.3) esta bem longe do centro geometrico da
        # imagem (240 pra 480px de altura) -- confirmado comparando
        # position_camera_m com medida de regua (dava 10.5cm de erro em
        # y pra um objeto a 4cm do eixo, e com cy~254 bate ~5cm). Ate
        # rodar uma calibracao de verdade (camera_calibration + apontar
        # color_info_url), sobrescreve aqui. -1 desliga o remendo e usa
        # o cy do camera_info normalmente.
        self.declare_parameter("cy_override", 253.92)

        # Mesmo problema no fx: camera_info diz 358, mas medido em
        # 2026-10-19 com regua (objeto a 0.42 m, profundidade conferida,
        # movido 10 cm de lado -> deslocou 108 px) da 108*0.42/0.10 = 454.
        # Com 358 o x lateral saia ~27% maior que o real. So o fx: fy/cy
        # continuam como estavam (o z do pick foi ajustado em cima deles).
        # -1 desliga e usa o fx do camera_info.
        self.declare_parameter("fx_override", 454.0)

        # ----------------------------
        # TF e seleção do alvo
        # ----------------------------
        self.declare_parameter("target_frame", "base_link")
        self.declare_parameter("target_class", "")
        self.declare_parameter("visualize", True)
        # Sem a TF do instante da foto, usar a "mais recente" dá posição
        # errada se o braço acabou de se mexer (a TF chegou a ficar ~6s
        # atrasada: braço na cam_pose e a conta ainda com a home). False:
        # descarta a posição 3D desse frame em vez de chutar.
        self.declare_parameter("tf_fallback", False)

        self.model_path = self.get_parameter("model_path").value
        self.tf_fallback = bool(self.get_parameter("tf_fallback").value)
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
        self.cy_override = float(
            self.get_parameter("cy_override").value
        )
        self.fx_override = float(
            self.get_parameter("fx_override").value
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

        # target_class precisa poder mudar em tempo real (o start_task troca
        # por pedido, via /rav_vision_3d/set_parameters) -- sem esse
        # callback o valor lido acima ficava congelado pro resto da
        # execução e o filtro de classe em synced_callback nunca via a
        # mudança.
        self.add_on_set_parameters_callback(self._on_parameter_change)

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
        # O listener roda num nó SÓ DELE, com thread própria. Com
        # TransformListener(self, spin_thread=True) a thread do listener
        # ganha o nó inteiro -- inclusive a assinatura das imagens -- e
        # metade das vezes era ela que rodava o YOLO (~1.5 s): o /tf ficava
        # parado e a TF chegava 1-6 s atrasada (braço já na cam_pose e a
        # conta ainda com a home).
        self.tf_buffer = Buffer()
        self._tf_node = rclpy.create_node(f"{self.get_name()}_tf")
        self.tf_listener = TransformListener(
            self.tf_buffer,
            self._tf_node,
            spin_thread=True,
        )
        # Diagnóstico: idade da TF câmera -> target_frame que este nó tem.
        self._camera_frame = None
        threading.Thread(target=self._vigiar_tf, daemon=True).start()

        # depth=1: com a inferencia mais lenta que a camera, uma fila maior
        # so acumula frames velhos (chegava a ~2.5s de atraso); assim
        # sempre processa o frame mais recente.
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
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

    def _on_parameter_change(self, params):
        for param in params:
            if param.name == "target_class":
                self.target_class = str(param.value)
                self.get_logger().info(
                    f"target_class atualizado para '{self.target_class}'"
                )
        return SetParametersResult(successful=True)

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

        self.fx = (
            self.fx_override
            if self.fx_override >= 0.0
            else float(msg.k[0])
        )
        self.fy = float(msg.k[4])
        self.cx = float(msg.k[2])
        self.cy = (
            self.cy_override
            if self.cy_override >= 0.0
            else float(msg.k[5])
        )

    def synced_callback(self, color_msg: Image, depth_msg: Image):
        """
        Executa YOLO no RGB e obtém profundidade correspondente
        no mapa de depth alinhado ao RGB.
        """
        self._camera_frame = color_msg.header.frame_id

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
        Obtém a profundidade do objeto como a superfície mais próxima
        dentro da bounding box.

        Não usa a mediana da região central: a imagem de profundidade
        registrada fica deslocada da RGB (cresce longe do centro da
        imagem), e medido em 2026-10-19 metade da bbox caía no fundo --
        objeto a 0.42 m virava 0.80 m e o x saía 2x maior. O fundo está
        sempre atrás do objeto, então o grupo mais próximo é o objeto.
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

        # Bbox inteira (não só o centro): com o deslocamento depth/RGB o
        # objeto pode estar só numa lateral da caixa.
        roi = depth_m[y1:y2, x1:x2]

        valid = roi[np.isfinite(roi)]

        valid = valid[
            (valid >= self.min_depth_m)
            & (valid <= self.max_depth_m)
        ]

        if valid.size < self.min_valid_depth_pixels:
            return None

        # Superfície mais próxima: percentil baixo (ignora pontos de ruído
        # isolados ainda mais perto) e o grupo de pixels logo atrás dele.
        perto = float(np.percentile(valid, 15))
        objeto = valid[
            (valid >= perto - 0.02)
            & (valid <= perto + 0.03)
        ]

        if objeto.size < self.min_valid_depth_pixels:
            return None

        return float(np.median(objeto)), u, v, int(objeto.size)

    def _vigiar_tf(self):
        """A cada 5 s mede quão velha está a TF câmera -> target_frame no
        buffer deste nó. Acima de 0.5 s avisa (a posição 3D sai errada ou é
        descartada); de 30 em 30 s registra mesmo estando ok."""
        ultimo_info = 0.0
        while rclpy.ok():
            time.sleep(5.0)
            if self._camera_frame is None:
                continue
            try:
                t = self.tf_buffer.lookup_transform(
                    self.target_frame, self._camera_frame, Time()
                ).header.stamp
            except TransformException as exc:
                self.get_logger().warn(f"vigia TF: sem TF ({exc})")
                continue
            if t.sec == 0 and t.nanosec == 0:
                continue  # só TFs estáticas na cadeia
            idade = (
                self.get_clock().now().nanoseconds * 1e-9
                - (t.sec + t.nanosec * 1e-9)
            )
            if idade > 0.5:
                self.get_logger().warn(f"vigia TF: TF atrasada {idade:.2f}s")
            elif time.monotonic() - ultimo_info > 30.0:
                ultimo_info = time.monotonic()
                self.get_logger().info(f"vigia TF: ok (atraso {idade:.2f}s)")

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
            # A camera fica na ponta da gripper (se move com o braco), entao
            # a transformacao camera->target muda a cada pose -- tem que
            # usar a TF no instante exato da foto (header.stamp), nao "a
            # mais recente disponivel". Antes usava Time() achando que o
            # braco ficava parado (ready) durante a deteccao; com o braco
            # em movimento isso dava posicao 3D errada, sem padrao fixo
            # pra corrigir depois (confirmado: mesma formula de correcao
            # batia numa deteccao e errava feio na proxima).
            try:
                transform = self.tf_buffer.lookup_transform(
                    self.target_frame,
                    point_camera.header.frame_id,
                    Time.from_msg(point_camera.header.stamp),
                    timeout=Duration(seconds=0.20)
                )
            except TransformException as exc:
                if not self.tf_fallback:
                    self.get_logger().warn(
                        f"TF no timestamp exato da deteccao indisponivel "
                        f"({exc}); posicao 3D descartada neste frame.",
                        throttle_duration_sec=2.0,
                    )
                    return None
                self.get_logger().warn(
                    f"TF no timestamp exato da deteccao indisponivel "
                    f"({exc}), usando a mais recente disponivel como "
                    "fallback (pode ficar impreciso se o braco estiver "
                    "em movimento)."
                )
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