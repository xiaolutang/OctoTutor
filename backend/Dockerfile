FROM python:3.12-slim

WORKDIR /app

# 1. 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 2. 复制应用代码
COPY app/ ./app/

# 3. 创建数据目录
RUN mkdir -p data/raw data/parsed data/images data/chroma_db data/evaluation

# 4. 暴露端口
EXPOSE 8000

# 5. 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
