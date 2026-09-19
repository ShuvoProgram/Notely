# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .
# API_INTERNAL_URL is read at build time for rewrites; the runtime env overrides it.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN pnpm --filter web build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S notely && adduser -S -G notely notely
COPY --from=build --chown=notely:notely /repo/apps/web/.next/standalone ./
COPY --from=build --chown=notely:notely /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=notely:notely /repo/apps/web/public ./apps/web/public
USER notely
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
