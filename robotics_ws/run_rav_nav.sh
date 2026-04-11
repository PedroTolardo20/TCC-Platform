#!/bin/bash
set -e

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
  echo -e "\n${RED}Encerrando processos do launch...${NC}"
  [[ -n "$BRINGUP_PID" ]] && kill "$BRINGUP_PID" 2>/dev/null || true
  [[ -n "$NAV_PID" ]] && kill "$NAV_PID" 2>/dev/null || true
  pkill -f rviz2 2>/dev/null || true
  pkill -f robot_state_publisher 2>/dev/null || true
  pkill -f joint_state_publisher 2>/dev/null || true
  pkill -f rav_platform_ctrl 2>/dev/null || true
  pkill -f planner_server 2>/dev/null || true
  pkill -f controller_server 2>/dev/null || true
  pkill -f bt_navigator 2>/dev/null || true
  pkill -f behavior_server 2>/dev/null || true
  pkill -f waypoint_follower 2>/dev/null || true
  pkill -f map_server 2>/dev/null || true
  pkill -f velocity_smoother 2>/dev/null || true
  pkill -f lifecycle_manager 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${GREEN}Limpando processos antigos...${NC}"
pkill -f rviz2 2>/dev/null || true
pkill -f robot_state_publisher 2>/dev/null || true
pkill -f joint_state_publisher 2>/dev/null || true
pkill -f rav_platform_ctrl 2>/dev/null || true
pkill -f planner_server 2>/dev/null || true
pkill -f controller_server 2>/dev/null || true
pkill -f bt_navigator 2>/dev/null || true
pkill -f behavior_server 2>/dev/null || true
pkill -f waypoint_follower 2>/dev/null || true
pkill -f map_server 2>/dev/null || true
pkill -f velocity_smoother 2>/dev/null || true
pkill -f lifecycle_manager 2>/dev/null || true

ros2 daemon stop 2>/dev/null || true
sleep 1
ros2 daemon start 2>/dev/null || true

echo -e "${GREEN}Subindo bringup...${NC}"
ros2 launch rav_bringup bringup.launch.py &
BRINGUP_PID=$!

echo -e "${GREEN}Esperando robot_state_publisher...${NC}"
until ros2 node list 2>/dev/null | grep -q "^/robot_state_publisher$"; do
  sleep 0.5
done

echo -e "${GREEN}Esperando rav_platform_ctrl...${NC}"
until ros2 node list 2>/dev/null | grep -q "^/rav_platform_ctrl$"; do
  sleep 0.5
done

echo -e "${GREEN}Bringup pronto!${NC}"

echo -e "${GREEN}Subindo nav...${NC}"
ros2 launch rav_nav2 rav_nav.launch.py &
NAV_PID=$!

echo -e "${GREEN}Esperando map_server aparecer...${NC}"
until ros2 node list 2>/dev/null | grep -q "^/map_server$"; do
  sleep 0.5
done

echo -e "${GREEN}Esperando map_server ficar ativo...${NC}"
until ros2 lifecycle get /map_server 2>/dev/null | grep -q "active"; do
  sleep 0.5
done

echo -e "${GREEN}Nav pronto!${NC}"

wait