# Dashboard Startup Configuration for Raspberry Pi

This guide explains how to set up the Personal Dashboard to start automatically on Raspberry Pi boot.

## Prerequisites

- Raspberry Pi with Raspberry Pi OS (or similar Linux distribution)
- pipenv installed and in PATH
- Dashboard application configured and tested
- User account (default: `pi`) with appropriate permissions

## Setup Instructions

### Step 1: Make the startup script executable

```bash
chmod +x /home/pi/IdeaProjects/mm/start_dashboard.sh
```

### Step 2: Update paths in the service file

Edit `personaldashboard.service` and update the following paths if your setup is different:

- `User=pi` - Change to your username if different
- `Group=pi` - Change to your group if different
- `WorkingDirectory=/home/pi/IdeaProjects/mm` - Update to your project path
- `ExecStart=/home/pi/IdeaProjects/mm/start_dashboard.sh` - Update to your script path
- All log paths in `StandardOutput` and `StandardError`

### Step 3: Copy the service file to systemd

```bash
sudo cp personaldashboard.service /etc/systemd/system/
```

### Step 4: Reload systemd and enable the service

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable personaldashboard.service

# Start the service now (optional - to test without rebooting)
sudo systemctl start personaldashboard.service
```

### Step 5: Verify the service is running

```bash
# Check service status
sudo systemctl status personaldashboard.service

# Check if it's enabled
sudo systemctl is-enabled personaldashboard.service
```

## Managing the Service

### Start the service
```bash
sudo systemctl start personaldashboard.service
```

### Stop the service
```bash
sudo systemctl stop personaldashboard.service
```

### Restart the service
```bash
sudo systemctl restart personaldashboard.service
```

### Disable auto-start on boot
```bash
sudo systemctl disable personaldashboard.service
```

### View service logs
```bash
# Service logs (systemd)
sudo journalctl -u personaldashboard.service -f

# Application logs
tail -f ~/.personal_dashboard/logs/startup.log

# Service output/error logs
tail -f ~/.personal_dashboard/logs/service.out.log
tail -f ~/.personal_dashboard/logs/service.err.log
```

## Troubleshooting

### Dashboard doesn't start on boot

1. **Check if the service is enabled:**
   ```bash
   sudo systemctl is-enabled personaldashboard.service
   ```
   Should return `enabled`

2. **Check service status:**
   ```bash
   sudo systemctl status personaldashboard.service
   ```

3. **Check the logs:**
   ```bash
   sudo journalctl -u personaldashboard.service -n 50
   tail -f ~/.personal_dashboard/logs/startup.log
   ```

4. **Verify paths are correct:**
   - Ensure `start_dashboard.sh` exists and is executable
   - Ensure the project directory path in the service file is correct
   - Ensure pipenv is in PATH (check with `which pipenv`)

5. **Test the script manually:**
   ```bash
   /home/pi/IdeaProjects/mm/start_dashboard.sh
   ```

### Dashboard starts but GUI doesn't show

1. **Check DISPLAY environment:**
   ```bash
   echo $DISPLAY
   ```
   Should be `:0` for the default display

2. **Ensure X server is running:**
   ```bash
   ps aux | grep X
   ```

3. **Check X authority:**
   ```bash
   ls -la ~/.Xauthority
   ```

4. **Try setting DISPLAY manually:**
   ```bash
   export DISPLAY=:0
   export XAUTHORITY=/home/pi/.Xauthority
   ```

5. **If using VNC or remote desktop, update DISPLAY:**
   - For VNC: `export DISPLAY=:1` (or appropriate display number)
   - Update the service file accordingly

### Permission issues

1. **Ensure the user has permission to run the service:**
   ```bash
   # Check if user can access the project directory
   ls -la /home/pi/IdeaProjects/mm
   ```

2. **Check pipenv permissions:**
   ```bash
   which pipenv
   pipenv --version
   ```

### Network connectivity issues

The script waits for network connectivity, but if your Raspberry Pi doesn't have internet at boot:

1. **Remove or modify the network check in `start_dashboard.sh`** if not needed
2. **Ensure network services start before the dashboard:**
   - The service file already includes `After=network.target`

### Service keeps restarting

If the service keeps restarting (crash loop):

1. **Check the logs for errors:**
   ```bash
   sudo journalctl -u personaldashboard.service -n 100
   ```

2. **Temporarily disable auto-restart to see the error:**
   - Edit `/etc/systemd/system/personaldashboard.service`
   - Change `Restart=always` to `Restart=no`
   - Run `sudo systemctl daemon-reload` and `sudo systemctl restart personaldashboard.service`

## Alternative: Using cron for startup

If you prefer using cron instead of systemd:

1. **Edit crontab:**
   ```bash
   crontab -e
   ```

2. **Add this line (runs at boot, waits 60 seconds for system to be ready):**
   ```bash
   @reboot sleep 60 && /home/pi/IdeaProjects/mm/start_dashboard.sh
   ```

## Manual Startup

To start the dashboard manually:

```bash
cd /home/pi/IdeaProjects/mm
pipenv run python -m dashboard.main --config config/config.yaml
```

Or create an alias in `~/.bashrc` or `~/.zshrc`:
```bash
alias start-dashboard='cd /home/pi/IdeaProjects/mm && pipenv run python -m dashboard.main --config config/config.yaml &'
```

## Notes

- The service is configured to restart automatically if it crashes
- Logs are stored in `~/.personal_dashboard/logs/`
- The service waits for network connectivity before starting
- GUI applications require the DISPLAY environment variable to be set
- Make sure your Raspberry Pi is set to boot to desktop (not CLI) if you need GUI
