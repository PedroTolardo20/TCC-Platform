import math
import time

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


def yaw_to_quat(yaw: float):
    # quaternion for yaw-only rotation
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


class PlatformCtrlNode(Node):
    def __init__(self):
        super().__init__('rav_platform_ctrl')

        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('cmd_timeout_s', 0.5)
        self.declare_parameter('publish_rate_hz', 50.0)

        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value
        self.odom_topic = self.get_parameter('odom_topic').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        self.cmd_timeout_s = float(self.get_parameter('cmd_timeout_s').value)
        self.rate_hz = float(self.get_parameter('publish_rate_hz').value)

        self.sub = self.create_subscription(Twist, cmd_vel_topic, self.on_cmd_vel, 10)
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        # state
        self.vx = 0.0
        self.wz = 0.0
        self.last_cmd_time = time.time()

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0

        self.last_update = time.time()
        self.timer = self.create_timer(1.0 / self.rate_hz, self.update)

        self.get_logger().info(f'Listening {cmd_vel_topic} and publishing {self.odom_topic} + TF {self.odom_frame}->{self.base_frame}')

    def on_cmd_vel(self, msg: Twist):
        self.vx = float(msg.linear.x)
        self.wz = float(msg.angular.z)
        self.last_cmd_time = time.time()

    def update(self):
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        if dt <= 0.0:
            return

        # stop if cmd_vel timed out
        if (now - self.last_cmd_time) > self.cmd_timeout_s:
            vx = 0.0
            wz = 0.0
        else:
            vx = self.vx
            wz = self.wz

        # integrate
        self.yaw += wz * dt
        self.x += vx * math.cos(self.yaw) * dt
        self.y += vx * math.sin(self.yaw) * dt

        qx, qy, qz, qw = yaw_to_quat(self.yaw)

        # TF odom->base_link
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.odom_frame
        t.child_frame_id = self.base_frame
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self.tf_broadcaster.sendTransform(t)

        # Odometry
        odom = Odometry()
        odom.header.stamp = t.header.stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = vx
        odom.twist.twist.angular.z = wz
        self.odom_pub.publish(odom)


def main():
    rclpy.init()
    node = PlatformCtrlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
