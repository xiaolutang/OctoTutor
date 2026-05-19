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
COPY package.json package-lock.json* ./

# 修改 @xlfoundry/auth-sdk-web 引用指向本地 SDK（已有 dist/ 构建产物）
RUN sed -i 's|"@xlfoundry/auth-sdk-web": "file:.*"|"@xlfoundry/auth-sdk-web": "file:./auth-sdk-web"|' package.json \
    && npm install

# 3. 复制项目源码
COPY next.config.ts tsconfig.json postcss.config.mjs eslint.config.mjs components.json ./
COPY src ./src
COPY public ./public

# 4. 构建 Next.js
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
