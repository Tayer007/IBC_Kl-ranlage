# IBC Wastewater Treatment - Cloudflared Daemon Setup

## Overview

Your IBC Wastewater Treatment application is now running as systemd services with cloudflared tunnel for remote access.

## Services Installed

1. **ibc-backend.service** - Flask backend server
2. **ibc-cloudflared.service** - Cloudflare tunnel daemon

Both services are configured to:
- Start automatically on boot
- Restart automatically if they crash
- Log to system journal and dedicated log files

## Service Management

Use the `manage_services.sh` script to manage the services:

```bash
# Get current tunnel URL
./manage_services.sh url

# Check service status
./manage_services.sh status

# View recent logs
./manage_services.sh logs

# Restart services
sudo ./manage_services.sh restart

# Stop services
sudo ./manage_services.sh stop

# Start services
sudo ./manage_services.sh start

# Uninstall services
sudo ./manage_services.sh uninstall
```

## Current Tunnel URL

Run `./manage_services.sh url` to get your current public URL. The URL changes each time the cloudflared service restarts.

Note: Free Cloudflare tunnels (trycloudflare.com) have no uptime guarantee and are for testing only. For production use, create a named tunnel with a Cloudflare account.

## Log Files

- Backend logs: `/home/fourat/IBC_Siedlungswasser_2/backend/backend.log`
- Cloudflared logs: `/home/fourat/IBC_Siedlungswasser_2/cloudflared.log`

## Service Files

- Backend service: `/etc/systemd/system/ibc-backend.service`
- Cloudflared service: `/etc/systemd/system/ibc-cloudflared.service`

## Manual Service Control

You can also use standard systemd commands:

```bash
# Check status
sudo systemctl status ibc-backend.service
sudo systemctl status ibc-cloudflared.service

# View logs
sudo journalctl -u ibc-backend.service -f
sudo journalctl -u ibc-cloudflared.service -f

# Restart
sudo systemctl restart ibc-backend.service
sudo systemctl restart ibc-cloudflared.service

# Stop
sudo systemctl stop ibc-backend.service
sudo systemctl stop ibc-cloudflared.service

# Start
sudo systemctl start ibc-backend.service
sudo systemctl start ibc-cloudflared.service
```

## Automatic Startup

Both services are enabled and will start automatically when the system boots.

To disable automatic startup:
```bash
sudo systemctl disable ibc-backend.service
sudo systemctl disable ibc-cloudflared.service
```

To enable automatic startup again:
```bash
sudo systemctl enable ibc-backend.service
sudo systemctl enable ibc-cloudflared.service
```

## Troubleshooting

### Backend not starting
Check logs: `sudo journalctl -u ibc-backend.service -n 50`

### Cloudflared tunnel not working
1. Check if backend is running: `curl http://localhost:5000/api/health`
2. Check cloudflared logs: `tail -50 /home/fourat/IBC_Siedlungswasser_2/cloudflared.log`

### Can't access through tunnel URL
1. Get current URL: `./manage_services.sh url`
2. Wait a few seconds for tunnel to establish
3. Try accessing `/api/health` endpoint first

## Notes

- The frontend is built and served from the backend at `/home/fourat/IBC_Siedlungswasser_2/frontend/dist`
- Backend runs on port 5000 internally
- Hardware mode is set to 'mock' in the service file - change the Environment variable in `/etc/systemd/system/ibc-backend.service` if needed
- After changing service files, run: `sudo systemctl daemon-reload && sudo systemctl restart ibc-backend.service`
