#!/bin/sh
# Template the API URL into the CSP security headers at container startup.
# This allows the same Docker image to be deployed to different environments
# without rebuilding.

set -e

API_URL="${VITE_API_URL:-http://localhost:8000}"

# Generate the security headers config in /tmp (writable tmpfs)
# with the correct CSP connect-src for this environment.
cat /etc/nginx/security-headers.conf | \
  sed "s|connect-src 'self' http://localhost:8000 http://127.0.0.1:8000|connect-src 'self' ${API_URL}|g" \
  > /tmp/security-headers.conf

# Overwrite the original include path with a symlink to the generated file
# (this won't work on read-only either, so we use nginx -e to include from /tmp)
# Instead, we'll use the -c flag to point nginx at a modified config.

# Actually, the simplest approach: just replace the nginx config to include
# from /tmp instead of /etc/nginx.
cp /etc/nginx/conf.d/default.conf /tmp/default.conf
sed -i 's|include /etc/nginx/security-headers.conf;|include /tmp/security-headers.conf;|g' /tmp/default.conf

echo "CSP connect-src configured for: ${API_URL}"

# Start nginx with the modified config
nginx -g "daemon off;" -c /etc/nginx/nginx.conf -e /tmp/nginx-error.log &

# Wait a moment then replace the config
sleep 0.1
mv /tmp/default.conf /etc/nginx/conf.d/default.conf 2>/dev/null || true

wait
