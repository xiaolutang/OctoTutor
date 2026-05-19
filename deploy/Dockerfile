# ===== Stage 1: Builder =====
FROM node:20-alpine AS builder

WORKDIR /build

# 1. 复制并构建 auth-sdk-web（package.json 中的 file:../xlfoundryTest/auth-sdk-web 依赖需要它）
COPY auth-sdk-web/package.json ./auth-sdk-web/
COPY auth-sdk-web/tsconfig.json ./auth-sdk-web/
COPY auth-sdk-web/vite.config.ts ./auth-sdk-web/
COPY auth-sdk-web/src ./auth-sdk-web/src

RUN cd auth-sdk-web && npm install && npx vite build

# 2. 复制项目 package 文件
COPY package.json package-lock.json* ./

# 修改 @xlfoundry/auth-sdk-web 引用指向本地构建产物
RUN sed -i 's|"@xlfoundry/auth-sdk-web": "file:.*"|"@xlfoundry/auth-sdk-web": "file:./auth-sdk-web"|' package.json

# 3. 安装依赖
RUN npm install

# 4. 复制源码并构建
COPY . .

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
