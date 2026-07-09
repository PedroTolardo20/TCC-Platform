#include <chrono>
#include <memory>
#include <string>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rclcpp/rclcpp.hpp>

using namespace std::chrono_literals;

class MockVisionPose final : public rclcpp::Node
{
public:
  MockVisionPose()
  : Node("mock_vision_pose")
  {
    frame_id_ = declare_parameter<std::string>("frame_id", "world");
    x_ = declare_parameter<double>("x", 0.30);
    y_ = declare_parameter<double>("y", 0.00);
    z_ = declare_parameter<double>("z", 0.90);
    repeat_count_ = declare_parameter<int>("repeat_count", 1);
    period_ms_ = declare_parameter<int>("period_ms", 500);

    publisher_ = create_publisher<geometry_msgs::msg::PoseStamped>(
      "/vision/object_pose", rclcpp::QoS(10));

    timer_ = create_wall_timer(
      std::chrono::milliseconds(period_ms_),
      std::bind(&MockVisionPose::publish_pose, this));

    RCLCPP_INFO(
      get_logger(),
      "Mock vision ready. Will publish target in frame '%s': [%.3f, %.3f, %.3f].",
      frame_id_.c_str(), x_, y_, z_);
  }

private:
  void publish_pose()
  {
    geometry_msgs::msg::PoseStamped msg;
    msg.header.stamp = now();
    msg.header.frame_id = frame_id_;
    msg.pose.position.x = x_;
    msg.pose.position.y = y_;
    msg.pose.position.z = z_;
    msg.pose.orientation.w = 1.0;

    publisher_->publish(msg);
    ++published_;

    RCLCPP_INFO(
      get_logger(),
      "Published mock object pose %d/%d.",
      published_, repeat_count_);

    if (published_ >= repeat_count_) {
      timer_->cancel();
      RCLCPP_INFO(get_logger(), "Mock vision completed.");
    }
  }

  std::string frame_id_;
  double x_{};
  double y_{};
  double z_{};
  int repeat_count_{};
  int period_ms_{};
  int published_{0};

  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MockVisionPose>());
  rclcpp::shutdown();
  return 0;
}
