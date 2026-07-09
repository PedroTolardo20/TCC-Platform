#!/usr/bin/env python3
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint


class SendHomeGoal(Node):
    def __init__(self):
        super().__init__("rav_send_home_goal")
        self.client = ActionClient(
            self,
            FollowJointTrajectory,
            "/arm_controller/follow_joint_trajectory",
        )

    def send(self):
        if not self.client.wait_for_server(timeout_sec=20.0):
            self.get_logger().error("arm_controller action server not available.")
            return False

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = [
            "shoulder_joint",
            "elbow_joint",
            "wrist_joint",
        ]

        point = JointTrajectoryPoint()
        point.positions = [-0.4200, 1.1800, 0.8240]
        point.velocities = [0.0, 0.0, 0.0]
        point.time_from_start = Duration(sec=2)
        goal.trajectory.points = [point]

        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=25.0)

        if future.result() is None:
            self.get_logger().error("Timed out while sending home goal.")
            return False

        handle = future.result()
        if not handle.accepted:
            self.get_logger().error("Home goal was rejected.")
            return False

        self.get_logger().info("Home goal accepted.")
        return True


def main():
    rclpy.init()
    node = SendHomeGoal()
    node.send()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
