#!/bin/bash

GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Subindo bringup...${NC}"
ros2 launch rav_bringup bringup.launch.py &

echo -e "${GREEN}Esperando robot_state_publisher...${NC}"
until ros2 node list | grep -q robot_state_publisher; do
  sleep 0.5
done

echo -e "${GREEN}Bringup pronto!${NC}"

echo -e "${GREEN}Subindo nav...${NC}"
ros2 launch rav_nav2 rav_nav.launch.py &

echo -e "${GREEN}Esperando map_server ficar ativo...${NC}"
until ros2 lifecycle get /map_server | grep -q "active"; do
  sleep 0.5
done

echo -e "${GREEN}Nav pronto!${NC}"