#!/usr/bin/env bash
set -e
sudo systemctl stop pinsheet
cd /opt/pinsheet-server
git pull
sudo systemctl start pinsheet
sudo systemctl status pinsheet --no-pager
