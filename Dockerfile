FROM python:3.14

# 从官方镜像直接拷贝 uv 及其工具
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1. 仅复制配置文件（利用 Docker 缓存层）
COPY pyproject.toml .
# 如果你有 uv.lock 也建议复制，确保版本完全一致
# COPY uv.lock . 

# 2. 安装依赖到系统环境 (--system)
# --no-cache 减小镜像体积
RUN uv pip install --system --no-cache -r pyproject.toml

# 3. 复制源代码
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
