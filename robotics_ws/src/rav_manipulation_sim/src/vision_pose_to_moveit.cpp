#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <thread>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/rclcpp.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <tf2/exceptions.h>
#include <tf2/time.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

using namespace std::chrono_literals;

class VisionPoseToMoveIt final : public rclcpp::Node
{
public:
  VisionPoseToMoveIt()
  : Node("vision_pose_to_moveit")
  {
    group_name_ = declare_parameter<std::string>("group_name", "rav_arm");
    tcp_link_ = declare_parameter<std::string>("tcp_link", "gripper_mount");
    object_topic_ = declare_parameter<std::string>(
      "object_topic", "/vision/object_pose");
    planning_time_ = declare_parameter<double>("planning_time", 5.0);
    position_tolerance_ = declare_parameter<double>("position_tolerance", 0.015);
    velocity_scale_ = declare_parameter<double>("velocity_scale", 0.20);
    acceleration_scale_ = declare_parameter<double>("acceleration_scale", 0.15);
  }

  void initialize()
  {
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

    move_group_ = std::make_shared<moveit::planning_interface::MoveGroupInterface>(
      shared_from_this(), group_name_);

    move_group_->setEndEffectorLink(tcp_link_);
    move_group_->setPlanningTime(planning_time_);
    move_group_->setGoalPositionTolerance(position_tolerance_);
    move_group_->setMaxVelocityScalingFactor(velocity_scale_);
    move_group_->setMaxAccelerationScalingFactor(acceleration_scale_);

    planning_frame_ = move_group_->getPlanningFrame();
    RCLCPP_INFO(
      get_logger(),
      "MoveIt ready. group='%s', TCP='%s', planning_frame='%s'.",
      group_name_.c_str(), tcp_link_.c_str(), planning_frame_.c_str());

    add_table_collision();

    subscription_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      object_topic_,
      rclcpp::QoS(10),
      std::bind(&VisionPoseToMoveIt::on_object_pose, this, std::placeholders::_1));

    RCLCPP_INFO(
      get_logger(),
      "Waiting for detection on '%s'.",
      object_topic_.c_str());
  }

private:
  void add_table_collision()
  {
    moveit_msgs::msg::CollisionObject table;
    table.header.frame_id = planning_frame_;
    table.id = "pick_table";

    shape_msgs::msg::SolidPrimitive primitive;
    primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
    primitive.dimensions.resize(3);
    primitive.dimensions[shape_msgs::msg::SolidPrimitive::BOX_X] = 0.50;
    primitive.dimensions[shape_msgs::msg::SolidPrimitive::BOX_Y] = 0.50;
    primitive.dimensions[shape_msgs::msg::SolidPrimitive::BOX_Z] = 0.80;

    geometry_msgs::msg::Pose table_pose;
    table_pose.position.x = 0.70;
    table_pose.position.y = 0.00;
    table_pose.position.z = 0.40;
    table_pose.orientation.w = 1.0;

    table.primitives.push_back(primitive);
    table.primitive_poses.push_back(table_pose);
    table.operation = moveit_msgs::msg::CollisionObject::ADD;

    planning_scene_.applyCollisionObject(table);
    RCLCPP_INFO(get_logger(), "Table collision object added to MoveIt planning scene.");
  }

  void on_object_pose(const geometry_msgs::msg::PoseStamped::SharedPtr message)
  {
    if (busy_.exchange(true)) {
      RCLCPP_WARN(get_logger(), "A target is already being processed; ignoring duplicate detection.");
      return;
    }

    auto target = *message;
    std::thread(
      [this, target]() {
        process_target(target);
        busy_.store(false);
      }).detach();
  }

  void process_target(const geometry_msgs::msg::PoseStamped & source)
  {
    geometry_msgs::msg::PoseStamped target;

    try {
      if (source.header.frame_id.empty()) {
        RCLCPP_ERROR(get_logger(), "Detection has empty frame_id; ignored.");
        return;
      }

      if (source.header.frame_id == planning_frame_) {
        target = source;
      } else {
        const auto transform = tf_buffer_->lookupTransform(
          planning_frame_,
          source.header.frame_id,
          tf2::TimePointZero,
          tf2::durationFromSec(1.0));

        tf2::doTransform(source, target, transform);
      }
    } catch (const tf2::TransformException & ex) {
      RCLCPP_ERROR(
        get_logger(),
        "Could not transform object from '%s' to '%s': %s",
        source.header.frame_id.c_str(),
        planning_frame_.c_str(),
        ex.what());
      return;
    }

    RCLCPP_INFO(
      get_logger(),
      "Object target in %s: x=%.3f, y=%.3f, z=%.3f.",
      planning_frame_.c_str(),
      target.pose.position.x,
      target.pose.position.y,
      target.pose.position.z);

    // No fixed 'pre_grasp' state is used. The supplied coordinate is the
    // dynamic TCP target produced by perception / grasp logic.
    move_group_->setStartStateToCurrentState();
    move_group_->clearPoseTargets();
    move_group_->setPositionTarget(
      target.pose.position.x,
      target.pose.position.y,
      target.pose.position.z,
      tcp_link_);

    moveit::planning_interface::MoveGroupInterface::Plan plan;
    const auto planned = move_group_->plan(plan);

    if (planned != moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_ERROR(get_logger(), "MoveIt could not plan to the received coordinate.");
      move_group_->clearPoseTargets();
      return;
    }

    RCLCPP_INFO(get_logger(), "Plan found. Executing through arm_controller.");
    const auto executed = move_group_->execute(plan);

    if (executed == moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_INFO(get_logger(), "Target execution completed.");
    } else {
      RCLCPP_ERROR(get_logger(), "Plan was created but execution failed.");
    }

    move_group_->clearPoseTargets();
  }

  std::string group_name_;
  std::string tcp_link_;
  std::string object_topic_;
  std::string planning_frame_;
  double planning_time_{};
  double position_tolerance_{};
  double velocity_scale_{};
  double acceleration_scale_{};

  std::shared_ptr<moveit::planning_interface::MoveGroupInterface> move_group_;
  moveit::planning_interface::PlanningSceneInterface planning_scene_;
  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr subscription_;
  std::atomic_bool busy_{false};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<VisionPoseToMoveIt>();
  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(), 3);
  executor.add_node(node);

  std::thread spin_thread([&executor]() { executor.spin(); });

  try {
    node->initialize();
  } catch (const std::exception & ex) {
    RCLCPP_FATAL(node->get_logger(), "Initialization failed: %s", ex.what());
    executor.cancel();
    spin_thread.join();
    rclcpp::shutdown();
    return 1;
  }

  spin_thread.join();
  rclcpp::shutdown();
  return 0;
}
