#!/usr/bin/env bash
set -e
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose up -d --build
echo
echo "SKHY Premium Monitor is starting."
echo "Open: http://YOUR_VPS_IP:8080"
