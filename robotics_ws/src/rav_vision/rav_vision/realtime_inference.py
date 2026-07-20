import json
import cv2
import rclpy

from rclpy.node import Node
from std_msgs.msg import String
from ultralytics import YOLO


class RAVVisionRealtime(Node):
    def __init__(self):
        super().__init__("rav_vision_realtime")

        self.declare_parameter("model_path", "")
        self.declare_parameter("source", "0")
        self.declare_parameter("imgsz", 512)
        self.declare_parameter("conf", 0.25)
        self.declare_parameter("device", "cpu")

        self.model_path = self.get_parameter("model_path").value
        self.source = str(self.get_parameter("source").value)
        self.imgsz = int(self.get_parameter("imgsz").value)
        self.conf = float(self.get_parameter("conf").value)
        self.device = str(self.get_parameter("device").value)

        if self.model_path == "":
            raise ValueError("Informe o parâmetro model_path com o caminho do best_50epochs.pt")

        self.get_logger().info(f"Carregando modelo: {self.model_path}")
        self.model = YOLO(self.model_path)

        # Se source for "0", "1", "2", usa como câmera local
        if self.source.isdigit():
            video_source = int(self.source)
        else:
            video_source = self.source

        self.cap = cv2.VideoCapture(video_source)

        if not self.cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir a câmera/fonte de vídeo: {self.source}")

        self.publisher = self.create_publisher(String, "/rav_vision/detections", 10)

        self.timer = self.create_timer(0.03, self.process_frame)

        self.get_logger().info("Inferência em tempo real iniciada.")
        self.get_logger().info("Pressione Q na janela da câmera para encerrar.")

    def process_frame(self):
        ret, frame = self.cap.read()

        if not ret:
            self.get_logger().warn("Não foi possível ler o frame.")
            return

        results = self.model.predict(
            source=frame,
            imgsz=self.imgsz,
            conf=self.conf,
            device=self.device,
            verbose=False
        )

        result = results[0]
        detections = []

        for box in result.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            class_name = self.model.names[class_id]

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            detections.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "bbox": {
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2)
                }
            })

        msg = String()
        msg.data = json.dumps(detections)
        self.publisher.publish(msg)

        annotated_frame = result.plot()
        cv2.imshow("RAV Vision - YOLO26 Realtime", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.get_logger().info("Encerrando...")
            rclpy.shutdown()

    def destroy_node(self):
        if hasattr(self, "cap"):
            self.cap.release()

        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = RAVVisionRealtime()

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
