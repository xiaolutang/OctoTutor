# ===== Stage 1: Builder =====
FROM node:20-alpine AS builder

WORKDIR /build

# 1. 复制 auth-sdk-web（包含已构建的 dist/ 和源码）
COPY auth-sdk-web/package.json ./auth-sdk-web/
COPY auth-sdk-web/tsconfig.json ./auth-sdk-web/
COPY auth-sdk-web/vite.config.ts ./auth-sdk-web/
COPY auth-sdk-web/src ./auth-sdk-web/src
COPY auth-sdk-web/dist ./auth-sdk-web/dist

# 2. 复制项目 package 文件并安装依赖
COPY frontend/package.json frontend/package-lock.json* ./

# 修改 @xlfoundry/auth-sdk-web 引用指向本地 SDK（已有 dist/ 构建产物）
RUN sed -i 's|"@xlfoundry/auth-sdk-web": "file:.*"|"@xlfoundry/auth-sdk-web": "file:./auth-sdk-web"|' package.json \
    && npm install --legacy-peer-deps

# 3. 复制项目源码
COPY frontend/next.config.ts frontend/tsconfig.json frontend/postcss.config.mjs frontend/eslint.config.mjs frontend/components.json ./
COPY frontend/src ./src
COPY frontend/public ./public

# 4. 线上构建时删除开发专用页面（本地构建保留）
ARG EXCLUDE_DEV=false
RUN if [ "$EXCLUDE_DEV" = "true" ]; then rm -rf ./src/app/dev; fi

# 5. 构建 Next.js
RUN npm run build --webpack

# ===== Stage 2: Runtime =====
FROM node:20-alpine

WORKDIR /app

# 复制 standalone 产物
COPY --from=builder /build/.next/standalone ./
COPY --from=builder /build/.next/static ./.next/static
COPY --from=builder /build/public ./public

ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

EXPOSE 3000

CMD ["node", "server.js"]
