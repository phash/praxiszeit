# Build stage
# node:22-alpine — Node 20 ist seit 2026-04-30 EOL (keine Security-Patches mehr);
# 22 ist Active LTS. Nur Build-Stage (Runtime-Image ist nginx:alpine).
FROM node:22-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
