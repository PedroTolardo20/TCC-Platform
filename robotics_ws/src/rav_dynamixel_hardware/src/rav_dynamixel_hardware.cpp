#include "rav_dynamixel_hardware/rav_dynamixel_hardware.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "dynamixel_sdk/dynamixel_sdk.h"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/rclcpp.hpp"

namespace rav_dynamixel_hardware
{

static constexpr double PROTOCOL_VERSION = 2.0;
static constexpr double TICKS_PER_RAD = 4096.0 / (2.0 * M_PI);

static constexpr uint16_t ADDR_OPERATING_MODE = 11;
static constexpr uint16_t ADDR_TORQUE_ENABLE = 64;
static constexpr uint16_t ADDR_HARDWARE_ERROR_STATUS = 70;
static constexpr uint16_t ADDR_PROFILE_ACCELERATION = 108;
static constexpr uint16_t ADDR_PROFILE_VELOCITY = 112;
static constexpr uint16_t ADDR_GOAL_POSITION = 116;
static constexpr uint16_t ADDR_PRESENT_VELOCITY = 128;
static constexpr uint16_t ADDR_PRESENT_POSITION = 132;

static constexpr uint8_t TORQUE_OFF = 0;
static constexpr uint8_t TORQUE_ON = 1;
static constexpr uint8_t POSITION_CONTROL_MODE = 3;

int RavDynamixelHardware::get_int_param_(const std::string & name, int default_value) const
{
  const auto it = info_.hardware_parameters.find(name);
  if (it == info_.hardware_parameters.end()) {
    return default_value;
  }
  return std::stoi(it->second);
}

std::string RavDynamixelHardware::get_string_param_(
  const std::string & name,
  const std::string & default_value) const
{
  const auto it = info_.hardware_parameters.find(name);
  if (it == info_.hardware_parameters.end()) {
    return default_value;
  }
  return it->second;
}

bool RavDynamixelHardware::get_bool_param_(const std::string & name, bool default_value) const
{
  const auto it = info_.hardware_parameters.find(name);
  if (it == info_.hardware_parameters.end()) {
    return default_value;
  }

  const auto & value = it->second;
  return value == "true" || value == "True" || value == "1";
}

hardware_interface::CallbackReturn RavDynamixelHardware::on_init(
  const hardware_interface::HardwareInfo & info)
{
  if (hardware_interface::SystemInterface::on_init(info) !=
      hardware_interface::CallbackReturn::SUCCESS)
  {
    return hardware_interface::CallbackReturn::ERROR;
  }

  if (info_.joints.empty()) {
    RCLCPP_ERROR(rclcpp::get_logger("RavDynamixelHardware"), "Nenhuma junta declarada.");
    return hardware_interface::CallbackReturn::ERROR;
  }

  dry_run_ = get_bool_param_("dry_run", true);
  enable_motors_ = get_bool_param_("enable_motors", false);
  device_ = get_string_param_(
    "device",
    "/dev/serial/by-id/usb-CM-900_ROBOTIS_Virtual_COM_Port-if00");
  baud_ = get_int_param_("baud", 1000000);
  profile_velocity_ = get_int_param_("profile_velocity", 8);
  profile_acceleration_ = get_int_param_("profile_acceleration", 3);

  const auto joint_count = info_.joints.size();

  hw_positions_.assign(joint_count, 0.0);
  hw_velocities_.assign(joint_count, 0.0);
  hw_commands_.assign(joint_count, 0.0);
  last_goal_ticks_.assign(joint_count, std::numeric_limits<int>::min());
  joint_configs_.resize(joint_count);

  for (std::size_t i = 0; i < joint_count; ++i) {
    const auto & joint = info_.joints[i];

    bool has_position_command = false;
    bool has_position_state = false;
    bool has_velocity_state = false;

    for (const auto & interface : joint.command_interfaces) {
      if (interface.name == hardware_interface::HW_IF_POSITION) {
        has_position_command = true;
      }
    }

    for (const auto & interface : joint.state_interfaces) {
      if (interface.name == hardware_interface::HW_IF_POSITION) {
        has_position_state = true;
      }
      if (interface.name == hardware_interface::HW_IF_VELOCITY) {
        has_velocity_state = true;
      }
    }

    if (!has_position_command || !has_position_state || !has_velocity_state) {
      RCLCPP_ERROR(
        rclcpp::get_logger("RavDynamixelHardware"),
        "Junta '%s' precisa de command position e state position/velocity.",
        joint.name.c_str());
      return hardware_interface::CallbackReturn::ERROR;
    }

    auto & cfg = joint_configs_[i];
    cfg.id = static_cast<int>(i + 1);
    cfg.direction = 1;
    cfg.zero_tick = 2048;
    cfg.min_tick = 0;
    cfg.max_tick = 4095;

    if (joint.parameters.count("id")) {
      cfg.id = std::stoi(joint.parameters.at("id"));
    }
    if (joint.parameters.count("direction")) {
      cfg.direction = std::stoi(joint.parameters.at("direction"));
    }
    if (joint.parameters.count("zero_tick")) {
      cfg.zero_tick = std::stoi(joint.parameters.at("zero_tick"));
    }
    if (joint.parameters.count("min_tick")) {
      cfg.min_tick = std::stoi(joint.parameters.at("min_tick"));
    }
    if (joint.parameters.count("max_tick")) {
      cfg.max_tick = std::stoi(joint.parameters.at("max_tick"));
    }

    RCLCPP_INFO(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Junta %s -> ID %d, direction %d, zero_tick %d",
      joint.name.c_str(),
      cfg.id,
      cfg.direction,
      cfg.zero_tick);
  }

  RCLCPP_INFO(
    rclcpp::get_logger("RavDynamixelHardware"),
    "Plugin RAV iniciado. dry_run=%s enable_motors=%s device=%s baud=%d",
    dry_run_ ? "true" : "false",
    enable_motors_ ? "true" : "false",
    device_.c_str(),
    baud_);

  return hardware_interface::CallbackReturn::SUCCESS;
}

std::vector<hardware_interface::StateInterface>
RavDynamixelHardware::export_state_interfaces()
{
  std::vector<hardware_interface::StateInterface> state_interfaces;

  for (std::size_t i = 0; i < info_.joints.size(); ++i) {
    state_interfaces.emplace_back(
      info_.joints[i].name,
      hardware_interface::HW_IF_POSITION,
      &hw_positions_[i]);

    state_interfaces.emplace_back(
      info_.joints[i].name,
      hardware_interface::HW_IF_VELOCITY,
      &hw_velocities_[i]);
  }

  return state_interfaces;
}

std::vector<hardware_interface::CommandInterface>
RavDynamixelHardware::export_command_interfaces()
{
  std::vector<hardware_interface::CommandInterface> command_interfaces;

  for (std::size_t i = 0; i < info_.joints.size(); ++i) {
    command_interfaces.emplace_back(
      info_.joints[i].name,
      hardware_interface::HW_IF_POSITION,
      &hw_commands_[i]);
  }

  return command_interfaces;
}

int RavDynamixelHardware::rad_to_tick_(std::size_t joint_index, double radians) const
{
  const auto & cfg = joint_configs_[joint_index];
  const int raw = static_cast<int>(
    std::lround(static_cast<double>(cfg.zero_tick) +
                static_cast<double>(cfg.direction) * radians * TICKS_PER_RAD));

  return std::clamp(raw, cfg.min_tick, cfg.max_tick);
}

double RavDynamixelHardware::tick_to_rad_(std::size_t joint_index, int tick) const
{
  const auto & cfg = joint_configs_[joint_index];
  return static_cast<double>(cfg.direction) *
         (static_cast<double>(tick - cfg.zero_tick) / TICKS_PER_RAD);
}

bool RavDynamixelHardware::dxl_write1_(
  int id,
  uint16_t address,
  uint8_t value,
  const std::string & label)
{
  uint8_t dxl_error = 0;
  const int result = packet_handler_->write1ByteTxRx(
    port_handler_,
    static_cast<uint8_t>(id),
    address,
    value,
    &dxl_error);

  if (result != COMM_SUCCESS) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "%s ID %d: %s",
      label.c_str(),
      id,
      packet_handler_->getTxRxResult(result));
    return false;
  }

  if (dxl_error != 0) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "%s ID %d: %s",
      label.c_str(),
      id,
      packet_handler_->getRxPacketError(dxl_error));
    return false;
  }

  return true;
}

bool RavDynamixelHardware::dxl_write4_(
  int id,
  uint16_t address,
  uint32_t value,
  const std::string & label)
{
  uint8_t dxl_error = 0;
  const int result = packet_handler_->write4ByteTxRx(
    port_handler_,
    static_cast<uint8_t>(id),
    address,
    value,
    &dxl_error);

  if (result != COMM_SUCCESS) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "%s ID %d: %s",
      label.c_str(),
      id,
      packet_handler_->getTxRxResult(result));
    return false;
  }

  if (dxl_error != 0) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "%s ID %d: %s",
      label.c_str(),
      id,
      packet_handler_->getRxPacketError(dxl_error));
    return false;
  }

  return true;
}

bool RavDynamixelHardware::dxl_read1_(
  int id,
  uint16_t address,
  uint8_t & value,
  const std::string & label)
{
  uint8_t dxl_error = 0;
  const int result = packet_handler_->read1ByteTxRx(
    port_handler_,
    static_cast<uint8_t>(id),
    address,
    &value,
    &dxl_error);

  if (result != COMM_SUCCESS || dxl_error != 0) {
    RCLCPP_WARN(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Falha lendo %s do ID %d",
      label.c_str(),
      id);
    return false;
  }

  return true;
}

bool RavDynamixelHardware::dxl_read4_(
  int id,
  uint16_t address,
  uint32_t & value,
  const std::string & label)
{
  uint8_t dxl_error = 0;
  const int result = packet_handler_->read4ByteTxRx(
    port_handler_,
    static_cast<uint8_t>(id),
    address,
    &value,
    &dxl_error);

  if (result != COMM_SUCCESS || dxl_error != 0) {
    RCLCPP_WARN(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Falha lendo %s do ID %d",
      label.c_str(),
      id);
    return false;
  }

  return true;
}

hardware_interface::CallbackReturn RavDynamixelHardware::on_activate(
  const rclcpp_lifecycle::State &)
{
  if (dry_run_) {
    hw_commands_ = hw_positions_;
    std::fill(hw_velocities_.begin(), hw_velocities_.end(), 0.0);

    RCLCPP_INFO(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Dry-run ativo: nenhuma porta serial será aberta.");

    return hardware_interface::CallbackReturn::SUCCESS;
  }

  if (!enable_motors_) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Modo real bloqueado: defina enable_motors=true no URDF.");
    return hardware_interface::CallbackReturn::ERROR;
  }

  port_handler_ = dynamixel::PortHandler::getPortHandler(device_.c_str());
  packet_handler_ = dynamixel::PacketHandler::getPacketHandler(PROTOCOL_VERSION);

  if (!port_handler_->openPort()) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Não foi possível abrir %s",
      device_.c_str());
    return hardware_interface::CallbackReturn::ERROR;
  }

  if (!port_handler_->setBaudRate(baud_)) {
    RCLCPP_ERROR(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Não foi possível configurar baud %d",
      baud_);
    port_handler_->closePort();
    return hardware_interface::CallbackReturn::ERROR;
  }

  RCLCPP_INFO(
    rclcpp::get_logger("RavDynamixelHardware"),
    "Porta Dynamixel aberta em %s @ %d bps",
    device_.c_str(),
    baud_);

  for (std::size_t i = 0; i < joint_configs_.size(); ++i) {
    const auto & cfg = joint_configs_[i];

    uint16_t model_number = 0;
    uint8_t dxl_error = 0;
    const int ping_result = packet_handler_->ping(
      port_handler_,
      static_cast<uint8_t>(cfg.id),
      &model_number,
      &dxl_error);

    if (ping_result != COMM_SUCCESS || dxl_error != 0) {
      RCLCPP_ERROR(
        rclcpp::get_logger("RavDynamixelHardware"),
        "Ping falhou para ID %d",
        cfg.id);
      port_handler_->closePort();
      return hardware_interface::CallbackReturn::ERROR;
    }

    uint8_t mode = 0;
    uint8_t hw_error = 0;
    uint32_t present_tick_raw = 0;

    dxl_read1_(cfg.id, ADDR_OPERATING_MODE, mode, "operating mode");
    dxl_read1_(cfg.id, ADDR_HARDWARE_ERROR_STATUS, hw_error, "hardware error");
    dxl_read4_(cfg.id, ADDR_PRESENT_POSITION, present_tick_raw, "present position");

    if (mode != POSITION_CONTROL_MODE) {
      RCLCPP_ERROR(
        rclcpp::get_logger("RavDynamixelHardware"),
        "ID %d está em Operating Mode %u. Esperado: 3.",
        cfg.id,
        mode);
      port_handler_->closePort();
      return hardware_interface::CallbackReturn::ERROR;
    }

    if (hw_error != 0) {
      RCLCPP_ERROR(
        rclcpp::get_logger("RavDynamixelHardware"),
        "ID %d com hardware_error_status=%u",
        cfg.id,
        hw_error);
      port_handler_->closePort();
      return hardware_interface::CallbackReturn::ERROR;
    }

    dxl_write1_(cfg.id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "Torque OFF");
    dxl_write4_(cfg.id, ADDR_PROFILE_ACCELERATION, profile_acceleration_, "Profile Acceleration");
    dxl_write4_(cfg.id, ADDR_PROFILE_VELOCITY, profile_velocity_, "Profile Velocity");

    const int present_tick = static_cast<int>(present_tick_raw);
    hw_positions_[i] = tick_to_rad_(i, present_tick);
    hw_commands_[i] = hw_positions_[i];
    hw_velocities_[i] = 0.0;
    last_goal_ticks_[i] = present_tick;

    RCLCPP_INFO(
      rclcpp::get_logger("RavDynamixelHardware"),
      "%s ID %d model %u tick=%d rad=%.4f",
      info_.joints[i].name.c_str(),
      cfg.id,
      model_number,
      present_tick,
      hw_positions_[i]);

    dxl_write1_(cfg.id, ADDR_TORQUE_ENABLE, TORQUE_ON, "Torque ON");
  }

  RCLCPP_WARN(
    rclcpp::get_logger("RavDynamixelHardware"),
    "MODO REAL ATIVO: os Dynamixel físicos podem se mover.");

  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn RavDynamixelHardware::on_deactivate(
  const rclcpp_lifecycle::State &)
{
  if (!dry_run_ && port_handler_ && packet_handler_) {
    for (const auto & cfg : joint_configs_) {
      dxl_write1_(cfg.id, ADDR_TORQUE_ENABLE, TORQUE_OFF, "Torque OFF");
    }

    port_handler_->closePort();

    RCLCPP_INFO(
      rclcpp::get_logger("RavDynamixelHardware"),
      "Torque OFF em todos os Dynamixel e porta fechada.");
  }

  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::return_type RavDynamixelHardware::read(
  const rclcpp::Time &,
  const rclcpp::Duration & period)
{
  if (dry_run_) {
    return hardware_interface::return_type::OK;
  }

  for (std::size_t i = 0; i < joint_configs_.size(); ++i) {
    const auto & cfg = joint_configs_[i];

    uint32_t pos_raw = 0;
    uint32_t vel_raw = 0;

    if (!dxl_read4_(cfg.id, ADDR_PRESENT_POSITION, pos_raw, "present position")) {
      return hardware_interface::return_type::ERROR;
    }

    if (!dxl_read4_(cfg.id, ADDR_PRESENT_VELOCITY, vel_raw, "present velocity")) {
      vel_raw = 0;
    }

    const double previous_position = hw_positions_[i];
    hw_positions_[i] = tick_to_rad_(i, static_cast<int>(pos_raw));

    const int32_t signed_vel = static_cast<int32_t>(vel_raw);
    if (signed_vel != 0) {
      hw_velocities_[i] =
        static_cast<double>(joint_configs_[i].direction) *
        static_cast<double>(signed_vel) * 0.229 * 2.0 * M_PI / 60.0;
    } else if (period.seconds() > 0.0) {
      hw_velocities_[i] = (hw_positions_[i] - previous_position) / period.seconds();
    } else {
      hw_velocities_[i] = 0.0;
    }
  }

  return hardware_interface::return_type::OK;
}

hardware_interface::return_type RavDynamixelHardware::write(
  const rclcpp::Time &,
  const rclcpp::Duration & period)
{
  if (dry_run_) {
    const double dt = period.seconds();

    for (std::size_t i = 0; i < hw_commands_.size(); ++i) {
      if (!std::isfinite(hw_commands_[i])) {
        hw_commands_[i] = hw_positions_[i];
      }

      hw_velocities_[i] = dt > 0.0 ? (hw_commands_[i] - hw_positions_[i]) / dt : 0.0;
      hw_positions_[i] = hw_commands_[i];
    }

    return hardware_interface::return_type::OK;
  }

  for (std::size_t i = 0; i < joint_configs_.size(); ++i) {
    if (!std::isfinite(hw_commands_[i])) {
      continue;
    }

    const int target_tick = rad_to_tick_(i, hw_commands_[i]);

    if (target_tick == last_goal_ticks_[i]) {
      continue;
    }

    if (!dxl_write4_(
        joint_configs_[i].id,
        ADDR_GOAL_POSITION,
        static_cast<uint32_t>(target_tick),
        "Goal Position"))
    {
      return hardware_interface::return_type::ERROR;
    }

    last_goal_ticks_[i] = target_tick;
  }

  return hardware_interface::return_type::OK;
}

}  // namespace rav_dynamixel_hardware

PLUGINLIB_EXPORT_CLASS(
  rav_dynamixel_hardware::RavDynamixelHardware,
  hardware_interface::SystemInterface)
