#!/bin/bash
# Update Cloudflare IP ranges for nginx realip module
# Install: crontab -e → 0 4 * * * /opt/engagic/deploy/nginx/cloudflare-ip-update.sh
#
# This script:
# 1. Fetches current Cloudflare IP ranges
# 2. Generates nginx config with set_real_ip_from directives
# 3. Tests nginx config before applying
# 4. Reloads nginx if config is valid

set -e

CONFIG_FILE="/etc/nginx/conf.d/cloudflare-realip.conf"
TEMP_FILE="/tmp/cloudflare-realip.conf.tmp"

echo "# Cloudflare Real IP Configuration" > "$TEMP_FILE"
echo "# Auto-generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$TEMP_FILE"
echo "# Source: https://www.cloudflare.com/ips/" >> "$TEMP_FILE"
echo "" >> "$TEMP_FILE"

echo "# IPv4 ranges" >> "$TEMP_FILE"
curl -s https://www.cloudflare.com/ips-v4 | while read ip; do
    [ -n "$ip" ] && echo "set_real_ip_from $ip;" >> "$TEMP_FILE"
done

echo "" >> "$TEMP_FILE"
echo "# IPv6 ranges" >> "$TEMP_FILE"
curl -s https://www.cloudflare.com/ips-v6 | while read ip; do
    [ -n "$ip" ] && echo "set_real_ip_from $ip;" >> "$TEMP_FILE"
done

echo "" >> "$TEMP_FILE"
echo "real_ip_header CF-Connecting-IP;" >> "$TEMP_FILE"
echo "real_ip_recursive on;" >> "$TEMP_FILE"

# Backup existing config
if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
fi

# Install new config
cp "$TEMP_FILE" "$CONFIG_FILE"

# Test nginx config
if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "Cloudflare IPs updated and nginx reloaded"
else
    echo "ERROR: nginx config test failed, reverting"
    [ -f "${CONFIG_FILE}.bak" ] && cp "${CONFIG_FILE}.bak" "$CONFIG_FILE"
    exit 1
fi

rm -f "$TEMP_FILE"
