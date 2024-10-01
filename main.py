import os
import jwt
import time
import asyncio
from tasks import suno_tasks

from PIL import Image

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import FileResponse

from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
from services.sunoCore import SunoCore
from services.midjourneyCore import MidjourneyCore

from datetime import datetime, timedelta

import config as cf

suno_core = SunoCore(cf.SUNO_SESSION, cf.SUNO_COOKIES)
midjourney_core = MidjourneyCore(cf.MIDJOURNEY_COOKIES)


midjourney_tasks = {}


class TaskStatusRequest(BaseModel):
    taskId: str

class GenerateSunoRequest(BaseModel):
    prompt: str
    make_instrumental: bool = False

class ImagineRequest(BaseModel):
    prompt: str
    mode: str

class VaryRequest(BaseModel):
    taskId: str
    index: int
    mode: str

class UpscaleRequest(BaseModel):
    taskId: str
    index: int
    mode: str

class RemixRequest(BaseModel):
    img_urls: list
    prompt: Optional[str] = None
    mode: str

class PanRequest(BaseModel):
    taskId: str
    index: int
    direction: int
    mode: str

class ZoomRequest(BaseModel):
    taskId: str
    index: int
    zoom_factor: int
    mode: str

class RerunRequest(BaseModel):
    taskId: str
    mode: str


def generate_token() -> str:
    now = datetime.now()
    date_str = now.strftime("%Y%m")
    payload = {
        "sub": "auth_token",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "date": date_str
    }
    token = jwt.encode(payload, cf.SECRET, algorithm=cf.ALGORITHM)
    return token

def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Отсутствует токен авторизации")

    try:
        payload = jwt.decode(authorization, cf.SECRET, algorithms=[cf.ALGORITHM])
        token_date = payload.get("date")
        current_date = datetime.now().strftime("%Y%m")
        if token_date != current_date:
            raise HTTPException(status_code=401, detail="Токен устарел")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Срок действия токена истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Неверный токен")



def add_task_to_dict(task_dict, task_id, status):
    task_dict[task_id] = status

def get_task_status(task_dict, task_id):
    return task_dict.get(task_id)

def update_task_status(task_dict, task_id, new_status):
    if task_id in task_dict:
        task_dict[task_id] = new_status

async def delete_old_files():
    directories = ["output/sunoTasks", "output/midjourneyTasks"]
    now = time.time()
    cutoff = now - 24 * 3600

    for directory in directories:
        if not os.path.exists(directory):
            continue

        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                file_mod_time = os.path.getmtime(file_path)
                if file_mod_time < cutoff:
                    try:
                        os.remove(file_path)
                        print(f"Удалён файл: {file_path}")
                    except Exception as e:
                        print(f"Ошибка при удалении файла {file_path}: {e}")

async def schedule_file_cleanup():
    while True:
        await delete_old_files()
        await asyncio.sleep(3600) 

@asynccontextmanager
async def lifespan(app: FastAPI):
    token_refresh_task = asyncio.create_task(suno_core.keep_token_alive())
    cleanup_task = asyncio.create_task(schedule_file_cleanup())
    yield
    token_refresh_task.cancel()
    cleanup_task.cancel()
    try:
        await token_refresh_task
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

# === SUNO API ===

@app.post("/generateSuno")
async def generate_suno(request: GenerateSunoRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    clip_ids = await suno_core.get_clip_ids(request.prompt, request.make_instrumental)
    if clip_ids:
        for clip_id in clip_ids:
            add_task_to_dict(suno_tasks, clip_id, "in_process")
            background_tasks.add_task(process_suno_task, clip_id)
        return {"taskIds": clip_ids}
    else:
        raise HTTPException(status_code=500, detail="Не удалось получить clip IDs")

@app.post("/statusSuno")
async def status_suno(request: TaskStatusRequest, authorization: str = Depends(verify_token)):
    status = get_task_status(suno_tasks, request.taskId)
    if status:
        return {"status": status}
    else:
        raise HTTPException(status_code=404, detail="Задача не найдена.")

@app.post("/getSong")
async def get_song(request: TaskStatusRequest, authorization: str = Depends(verify_token)):
    file_path = os.path.join("output/sunoTasks", f"{request.taskId}.mp3")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename=f"{request.taskId}.mp3")
    else:
        raise HTTPException(status_code=404, detail="Ошибка при получении задачи.")
    
async def process_suno_task(clip_id: str):
    try:
        await asyncio.wait_for(suno_core.download_mp3(clip_id), timeout=cf.TASK_TIMEOUT_SECONDS)
        update_task_status(suno_tasks, clip_id, "success")
    except asyncio.TimeoutError:
        print(f"Задача загрузки для {clip_id} превысила лимит времени.")
        update_task_status(suno_tasks, clip_id, "timeout")
    except Exception as e:
        print(f"Ошибка при скачивании MP3 для {clip_id}: {e}")
        update_task_status(suno_tasks, clip_id, "error")


# === MIDJOURNEY API ===

@app.post("/imagineMidjourney")
async def imagine_midjourney(request: ImagineRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.imagine(request.prompt, request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации изображения: {e}")

@app.post("/varyMidjourney")
async def vary_midjourney(request: VaryRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.vary(task_id=request.taskId, index=request.index, mode=request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании вариации: {e}")

@app.post("/upscaleMidjourney")
async def upscale_midjourney(request: UpscaleRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.upscale(task_id=request.taskId, index=request.index, mode=request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id, one_file=True)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при увеличении изображения: {e}")

@app.post("/remixMidjourney")
async def remix_midjourney(request: RemixRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.remix(images=request.img_urls, mode=request.mode, new_prompt=request.prompt)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(
            process_midjourney_task, task_id, one_file=True)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ошибка при ремиксе изображения: {e}")

@app.post("/panMidjourney")
async def pan_midjourney(request: PanRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.pan(task_id=request.taskId, index=request.index, direction=request.direction, mode=request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при панорамировании изображения: {e}")

@app.post("/zoomMidjourney")
async def zoom_midjourney(request: ZoomRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.zoom(task_id=request.taskId, index=request.index, zoom_factor=request.zoom_factor, mode=request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при зумировании изображения: {e}")

@app.post("/rerunMidjourney")
async def rerun_midjourney(request: RerunRequest, background_tasks: BackgroundTasks, authorization: str = Depends(verify_token)):
    try:
        task_id = await midjourney_core.rerun(task_id=request.taskId, mode=request.mode)
        add_task_to_dict(midjourney_tasks, task_id, "in_process")
        background_tasks.add_task(process_midjourney_task, task_id)
        return {"taskId": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при пересоздании изображения: {e}")

@app.post("/statusMidjourney")
async def status_midjourney(request: TaskStatusRequest, authorization: str = Depends(verify_token)):
    status = get_task_status(midjourney_tasks, request.taskId)
    if status:
        return {"status": status}
    else:
        raise HTTPException(status_code=404, detail="Задача не найдена.")

@app.get("/images/{task_id}_{index}.png")
async def serve_image(task_id: str, index: int):
    file_path = os.path.join("output/midjourneyTasks", f"{task_id}_{index}.png")
    
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Файл не найден")

@app.get("/preview/{task_id}.png")
async def serve_preview(task_id: str):
    preview_path = os.path.join("output/midjourneyTasks", f"{task_id}_preview.png")
    
    if os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Превью не найдено")


async def process_midjourney_task(task_id: str, one_file=False):
    try:
        await asyncio.wait_for(midjourney_core.save_images_in_thread(task_id=task_id, one_file=one_file), timeout=cf.TASK_TIMEOUT_SECONDS)            
        update_task_status(midjourney_tasks, task_id, "success")
        await make_preview(task_id)
    except asyncio.TimeoutError:
        print(f"Задача загрузки изображений для {task_id} превысила лимит времени.")
        update_task_status(midjourney_tasks, task_id, "timeout")
    except Exception as e:
        print(f"Ошибка при скачивании изображений для {task_id}: {e}")
        update_task_status(midjourney_tasks, task_id, "error")

async def make_preview(task_id: str):
    try:
        image_dir = os.path.join("output", "midjourneyTasks")
        
        images = []
        for index in range(0, 4):
            image_path = os.path.join(image_dir, f"{task_id}_{index}.png")
            if os.path.exists(image_path):
                images.append(Image.open(image_path))
            else:
                raise FileNotFoundError(f"Изображение с индексом {index} не найдено")
        
        if len(images) != 4:
            raise ValueError("Недостаточно изображений для создания превью")

        min_width = min(image.size[0] for image in images)
        min_height = min(image.size[1] for image in images)
        resized_images = [image.resize((min_width, min_height), Image.Resampling.LANCZOS) for image in images]

        combined_image = Image.new("RGB", (min_width * 2, min_height * 2))
        combined_image.paste(resized_images[0], (0, 0))
        combined_image.paste(resized_images[1], (min_width, 0))
        combined_image.paste(resized_images[2], (0, min_height))
        combined_image.paste(resized_images[3], (min_width, min_height))

        final_image = combined_image.resize((1024, 1024), Image.Resampling.LANCZOS)

        preview_path = os.path.join(image_dir, f"{task_id}_preview.png")
        final_image.save(preview_path)

        print(f"Превью успешно создано и сохранено: {preview_path}")
    except Exception as e:
        print(f"Ошибка при создании превью: {e}")
