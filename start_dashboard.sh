#!/bin/bash

# Dashboard Startup Script for Raspberry Pi
# This script starts the Personal Dashboard application

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Set up logging
LOG_DIR="$HOME/.personal_dashboard/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/startup.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting Personal Dashboard..."

# Check if pipenv is available
if ! command -v pipenv &> /dev/null; then
    log "ERROR: pipenv is not installed or not in PATH"
    exit 1
fi

# Wait for network to be available (useful for reboot scenarios)
log "Waiting for network connectivity..."
for i in {1..30}; do
    if ping -c 1 -W 1 8.8.8.8 &> /dev/null 2>&1; then
        log "Network is available"
        break
    fi
    if [ $i -eq 30 ]; then
        log "WARNING: Network not available after 30 attempts, continuing anyway..."
    fi
    sleep 1
done

# Wait a bit more for system to be fully ready
sleep 2

# Set display for GUI (important for Raspberry Pi)
export DISPLAY=:0

# Activate pipenv and run the dashboard
log "Activating pipenv environment and starting dashboard..."
cd "$SCRIPT_DIR"

# Use pipenv run to execute the dashboard
# The --config flag points to the config file
pipenv run python -m dashboard.main --config config/config.yaml >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    log "ERROR: Dashboard exited with code $EXIT_CODE"
    exit $EXIT_CODE
fi

log "Dashboard stopped"
