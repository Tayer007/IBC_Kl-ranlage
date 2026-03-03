#!/bin/bash

# IBC Wastewater Treatment - Service Management Script
# Hochschule Koblenz

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_SERVICE="ibc-backend.service"
CLOUDFLARED_SERVICE="ibc-cloudflared.service"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  IBC Wastewater Treatment - Service Manager                  ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "❌ This script must be run with sudo"
        exit 1
    fi
}

# Function to install services
install_services() {
    echo "📦 Installing systemd services..."

    # Copy service files to systemd directory
    cp "$SCRIPT_DIR/$BACKEND_SERVICE" /etc/systemd/system/
    cp "$SCRIPT_DIR/$CLOUDFLARED_SERVICE" /etc/systemd/system/

    # Reload systemd daemon
    systemctl daemon-reload

    echo "✅ Services installed"
}

# Function to enable services
enable_services() {
    echo "🔧 Enabling services..."
    systemctl enable $BACKEND_SERVICE
    systemctl enable $CLOUDFLARED_SERVICE
    echo "✅ Services enabled (will start on boot)"
}

# Function to start services
start_services() {
    echo "🚀 Starting services..."
    systemctl start $BACKEND_SERVICE
    sleep 3  # Wait for backend to start
    systemctl start $CLOUDFLARED_SERVICE
    sleep 5  # Wait for tunnel to establish
    echo "✅ Services started"
}

# Function to stop services
stop_services() {
    echo "🛑 Stopping services..."
    systemctl stop $CLOUDFLARED_SERVICE || true
    systemctl stop $BACKEND_SERVICE || true
    echo "✅ Services stopped"
}

# Function to restart services
restart_services() {
    echo "🔄 Restarting services..."
    stop_services
    start_services
}

# Function to show status
show_status() {
    echo "📊 Service Status:"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Backend Service:"
    systemctl status $BACKEND_SERVICE --no-pager || true
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Cloudflared Service:"
    systemctl status $CLOUDFLARED_SERVICE --no-pager || true
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Function to show logs
show_logs() {
    echo "📋 Recent Logs:"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Backend Logs (last 20 lines):"
    journalctl -u $BACKEND_SERVICE -n 20 --no-pager || true
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Cloudflared Logs (last 20 lines):"
    journalctl -u $CLOUDFLARED_SERVICE -n 20 --no-pager || true
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Function to get tunnel URL
get_tunnel_url() {
    echo "🔍 Fetching tunnel URL..."
    echo ""

    # Try to get URL from cloudflared log file
    LOG_FILE="$SCRIPT_DIR/cloudflared.log"
    if [ -f "$LOG_FILE" ]; then
        TUNNEL_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | tail -1)
    fi

    # Fallback to journalctl if log file doesn't have URL
    if [ -z "$TUNNEL_URL" ]; then
        TUNNEL_URL=$(journalctl -u $CLOUDFLARED_SERVICE -n 200 --no-pager | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
    fi

    if [ -n "$TUNNEL_URL" ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🌐 TUNNEL URL:"
        echo "   $TUNNEL_URL"
        echo ""
        echo "   📋 Access Points:"
        echo "      Dashboard:    $TUNNEL_URL"
        echo "      API Health:   $TUNNEL_URL/api/health"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    else
        echo "❌ Could not find tunnel URL. Check if cloudflared service is running:"
        echo "   sudo systemctl status $CLOUDFLARED_SERVICE"
    fi
}

# Function to uninstall services
uninstall_services() {
    echo "🗑️  Uninstalling services..."

    # Stop services
    stop_services

    # Disable services
    systemctl disable $BACKEND_SERVICE || true
    systemctl disable $CLOUDFLARED_SERVICE || true

    # Remove service files
    rm -f /etc/systemd/system/$BACKEND_SERVICE
    rm -f /etc/systemd/system/$CLOUDFLARED_SERVICE

    # Reload systemd daemon
    systemctl daemon-reload

    echo "✅ Services uninstalled"
}

# Main script logic
case "$1" in
    install)
        check_root
        install_services
        enable_services
        start_services
        echo ""
        get_tunnel_url
        ;;
    start)
        check_root
        start_services
        echo ""
        get_tunnel_url
        ;;
    stop)
        check_root
        stop_services
        ;;
    restart)
        check_root
        restart_services
        echo ""
        get_tunnel_url
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    url)
        get_tunnel_url
        ;;
    uninstall)
        check_root
        uninstall_services
        ;;
    *)
        echo "Usage: $0 {install|start|stop|restart|status|logs|url|uninstall}"
        echo ""
        echo "Commands:"
        echo "  install    - Install and start services (requires sudo)"
        echo "  start      - Start services (requires sudo)"
        echo "  stop       - Stop services (requires sudo)"
        echo "  restart    - Restart services (requires sudo)"
        echo "  status     - Show service status"
        echo "  logs       - Show recent logs"
        echo "  url        - Get current tunnel URL"
        echo "  uninstall  - Stop and remove services (requires sudo)"
        exit 1
        ;;
esac
