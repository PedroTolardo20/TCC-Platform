#ifndef RAV_DYNAMIXEL_HARDWARE__RAV_DYNAMIXEL_HARDWARE_HPP_
#define RAV_DYNAMIXEL_HARDWARE__RAV_DYNAMIXEL_HARDWARE_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include "hardware_interface/system_interface.hpp"
#include "rclcpp/duration.hpp"
#include "rclcpp/time.hpp"
#include "rclcpp_lifecycle/state.hpp"

namespace dynamixel
{
class PortHandler;
class PacketHandler;
}

namespace rav_dynamixel_hardware
{

struct JointConfig
{
  int id = 0;
  int direction = 1;
  int zero_tick = 2048;
  int min_tick = 0;
  int max_tick = 4095;
};

class RavDynamixelHardware : public hardware_interface::SystemInterface
{
public:
  hardware_interface::CallbackReturn on_init(
    const hardware_interface::HardwareInfo & info) override;

  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;

  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  hardware_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;

  hardware_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;

  hardware_interface::return_type read(
    const rclcpp::Time & time,
    const rclcpp::Duration & period) override;

  hardware_interface::return_type write(
    const rclcpp::Time & time,
    const rclcpp::Duration & period) override;

private:
  int get_int_param_(const std::string & name, int default_value) const;
  std::string get_string_param_(const std::string & name, const std::string & default_value) const;
  bool get_bool_param_(const std::string & name, bool default_value) const;

  int rad_to_tick_(std::size_t joint_index, double radians) const;
  double tick_to_rad_(std::size_t joint_index, int tick) const;

  bool dxl_write1_(int id, uint16_t address, uint8_t value, const std::string & label);
  bool dxl_write4_(int id, uint16_t address, uint32_t value, const std::string & label);
  bool dxl_read1_(int id, uint16_t address, uint8_t & value, const std::string & label);
  bool dxl_read4_(int id, uint16_t address, uint32_t & value, const std::string & label);

  bool dry_run_{true};
  bool enable_motors_{false};

  std::string device_;
  int baud_{1000000};
  int profile_velocity_{8};
  int profile_acceleration_{3};

  dynamixel::PortHandler * port_handler_{nullptr};
  dynamixel::PacketHandler * packet_handler_{nullptr};

  std::vector<JointConfig> joint_configs_;

  std::vector<double> hw_positions_;
  std::vector<double> hw_velocities_;
  std::vector<double> hw_commands_;
  std::vector<int> last_goal_ticks_;
};

}  // namespace rav_dynamixel_hardware

#endif
