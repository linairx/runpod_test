import os
import uuid
import time
import shutil
import asyncio
import requests
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

app = FastAPI()

# 加载 .env 文件（可选）
load_dotenv()

# --- 配置区 ---
UPLOAD_DIR = "data/temp_videos"
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_ID:
    print("错误：未配置 RunPod 密钥或 Endpoint ID！")

BASE_URL = "https://你的公网域名或IP" # RunPod 访问你服务器的地址

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# 挂载静态目录，让 RunPod 可以通过 URL 下载视频
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

# --- 核心逻辑 ---

def remove_file_after_delay(file_path: str, delay: int):
    """后台任务：延迟删除文件"""
    time.sleep(delay)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"【清理成功】文件已销毁: {file_path}")
    except Exception as e:
        print(f"【清理失败】{e}")

@app.post("/process-sam2")
async def handle_sam2_request(file: UploadFile, background_tasks: BackgroundTasks):
    # 1. 使用 UUID 生成唯一文件名，防止重名和被猜测
    file_ext = os.path.splitext(file.filename)[1]
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # 2. 保存文件到服务器本地
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    # 3. 注册 2 小时后自动删除的任务 (7200秒)
    background_tasks.add_task(remove_file_after_delay, file_path, 7200)

    # 4. 构造供 RunPod 下载的视频 URL
    video_public_url = f"{BASE_URL}/static/{unique_name}"

    # 5. 调用 RunPod Serverless API
    runpod_url = f"api.runpod.ai{RUNPOD_ENDPOINT_ID}/run"
    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": {
            "video_url": video_public_url,  # 告诉 RunPod 去哪里下载视频
            "command": "segment_everything"  # 你的自定义参数
        }
    }

    try:
        response = requests.post(runpod_url, json=payload, headers=headers)
        runpod_data = response.json()
        
        # 返回给前端的结果中包含 Job ID，前端可以用它查询进度
        return {
            "status": "queued",
            "job_id": runpod_data.get("id"),
            "video_url_on_server": video_public_url,
            "expires_in": "2 hours"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用 RunPod 失败: {str(e)}")

# --- 2025 增强方案：防止进程重启导致清理失效 ---
@app.on_event("startup")
async def start_janitor():
    """启动一个后台循环，每小时扫描一次并清理漏网之鱼"""
    async def janitor_loop():
        while True:
            now = time.time()
            for f in os.listdir(UPLOAD_DIR):
                p = os.path.join(UPLOAD_DIR, f)
                # 如果文件超过 2 小时未修改则删除
                if os.path.getmtime(p) < now - 7200:
                    try: os.remove(p)
                    except: pass
            await asyncio.sleep(3600) # 每小时巡检一次
    
    asyncio.create_task(janitor_loop())
