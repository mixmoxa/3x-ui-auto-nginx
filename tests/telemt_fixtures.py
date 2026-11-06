"""Frozen Telegram Manager templates (GPL-3.0, xPROMSx).

Source: telegram-web-proxy-manager@3e73ceac75f1b7a7008446fa14c5811a76418c42
lib/safety.py render_vhost/render_acme; telemt-web-manager.sh generate_renewal_hook.
The integration suite also checks the historical bytes against the authenticated real helper.
B/C below are exact render_vhost() outputs from TWPM PR #39,
7902daf8c6bd25854c6ebdd88ccd2b6fdd9d3d96 (safety.py Git blob
cae9c357309f6ae4bd6e6e5b59373a320f4a0e70).
All three outputs are unchanged at 3bf3fbea7fa77d662983f102e778a7b16e4a15ee
(safety.py Git blob 4ba6cd4c073e5b6d1bd419c1620de147cecd7b61).
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

# Canonical outputs, not a test-side approximation of the renderer.
SITE_DIGEST = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'

VHOST_KEEPALIVE = '''# Managed by telemt-web-manager v1. Manual changes require review.
upstream twpm_web_backend {
    server 127.0.0.1:18080;
    keepalive 32;
}
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
        proxy_pass http://twpm_web_backend;
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

VHOST_SITE = '''# Managed by telemt-web-manager v1. Manual changes require review.
# TWPM original site v0.3 sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
upstream twpm_web_backend {
    server 127.0.0.1:18080;
    keepalive 32;
}
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
        proxy_pass http://twpm_web_backend;
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
server {
    listen 127.0.0.1:18081;
    server_name _;
    root /var/www/telemt-web-manager;
    index index.html;
    absolute_redirect off;
    server_tokens off;
    autoindex off;
    charset utf-8;
    access_log off;
    error_log /dev/null crit;
    default_type application/octet-stream;
    types {
        text/html html;
        text/css css;
        image/svg+xml svg;
        image/x-icon ico;
        text/plain txt;
    }
    add_header Content-Security-Policy "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" always;
    error_page 404 /404.html;
    location / { try_files $uri $uri/ =404; }
}
'''

VHOSTS = {'legacy': VHOST, 'keepalive': VHOST_KEEPALIVE, 'site': VHOST_SITE}
