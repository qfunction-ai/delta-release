# Builder stage — install deps and build production bundle
FROM node:22-alpine AS builder

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN corepack enable && corepack prepare pnpm@10.9.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts && pnpm rebuild esbuild

COPY . .
RUN pnpm run build

# Generate security-headers.conf with the correct CSP connect-src
# This runs at build time so the API URL is baked in (same as Vite does)
RUN sed "s|connect-src 'self' http://localhost:8000 http://127.0.0.1:8000|connect-src 'self' ${VITE_API_URL}|g" \
    security-headers.conf > /tmp/security-headers.conf

# Runtime stage — nginx serves static assets (unprivileged image)
FROM nginxinc/nginx-unprivileged:1.27-alpine3.20

COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /tmp/security-headers.conf /etc/nginx/security-headers.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
