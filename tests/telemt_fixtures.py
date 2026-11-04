"""Frozen Telegram Manager v1.1.5 templates (GPL-3.0, xPROMSx).

Source: telegram-web-proxy-manager@3e73ceac75f1b7a7008446fa14c5811a76418c42
lib/safety.py render_vhost/render_acme; telemt-web-manager.sh generate_renewal_hook.
The integration suite also checks these bytes against the authenticated real helper.
"""

VHOST = '''# Managed by telemt-web-manager v1. Manual changes require review.
server {
    listen 127.0.0.1:7444 ssl http2 proxy_protocol;
    server_name telegram.example.com;
    set_real_ip_from 127.0.0.1;
    real_ip_header proxy_protocol;
    access_log off;
    error_log /dev/null crit;
    ssl_certificate /etc/letsencrypt/live/telegram.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/telegram.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 2m;
    client_body_timeout 90s;
    send_timeout 90s;
    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Host telegram.example.com;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Connection "";
        proxy_set_header Upgrade "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 90s;
        proxy_send_timeout 90s;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_next_upstream off;
    }
}
'''

ACME = '''# Managed by telemt-web-manager v1. Persistent ACME webroot.
server {
    listen 80;
    server_name telegram.example.com;
    access_log off;
    error_log /dev/null crit;
    location ^~ /.well-known/acme-challenge/ {
        root /var/lib/telemt-web-manager-acme;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 404; }
}
'''

HOOK = '''#!/bin/sh
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
'''
