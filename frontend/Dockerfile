# Multi-stage: build the static production bundle with Node, then serve
# it with nginx — the build toolchain never ships in the final image.
# VITE_API_BASE_URL is a build-time arg because Vite inlines env vars into
# the static JS at build time; there's no "runtime config" for a static
# SPA bundle, so the backend URL must be known when this image is built.

FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://localhost:5000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ---- Serve stage ----

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
