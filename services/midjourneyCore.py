import os
import time
import aiohttp
import asyncio
import concurrent.futures
import cloudscraper

scraper = cloudscraper.create_scraper()

class MidjourneyCore:
    def __init__(self, cookie):
        self.api_url = 'http://130.211.27.27/api/app/submit-jobs'
        self.cdn_url = 'https://cdn.midjourney.com'
        self.common_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0',
            'Content-Type': 'application/json',
            'Cookie': cookie,
            'x-csrf-protection': '1',
            'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Microsoft Edge";v="128"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
            'origin': 'https://www.midjourney.com',
            'referer': 'https://www.midjourney.com/imagine'
        }
        self.get_image_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 YaBrowser/24.7.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'ru,en;q=0.9,de;q=0.8',
            'Cache-Control': 'no-cache',
            'Cookie': '_gcl_au=1.1.1716045163.1724301709; _ga=GA1.1.481271850.1724301709; AMP_MKTG_437c42b22c=JTdCJTdE; cf_clearance=fpAxfvpmG1wmky2QN4UVRiB_JsefTz58Ec2Gvuqc1nE-1725367407-1.2.1.1-fMrZY3g683hemI0FKUQYkRrveMiYsqIBZzoyF0zLWoFZPK4rcPaQTeFo7egzzV2JoOk3j23hokV4LZ9NizOgESU6X2tLIjWKsKVSGbIG4zzFCxAu7R1rQ.ImT2wp7NruCE5A53xXMl4Q9ytVUVfY4hIBm0abbTfXe5BaTEgejXRMXgUeNiUp9sDZk6keRZbjilPEViPiZ0NVujdOA3SqzvRgKg6MNW8zvpsyjbkbRY1bvSLRa5zAaMtRUGuX1g4ANqHZcb6jeebqZbcSGKSO._XRra_ik.RI4fIrVh7omFDnj_.VF6XSBkkyHPgq0t53p.tVY4ur1.l4LM4MMPXN90ckMdmiE1Nq9qbZ0x4He0xw.gGM6pWMsg8cH49nEv6UYCVw3S1vl7bDUn8OV7v9SS3CXjBsT1FMxKdvjIVeD0A',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "YaBrowser";v="24.7", "Yowser";v="2.5"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1'
        }

    async def imagine(self, prompt, mode):
        payload = {
            "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
            'f': {'mode': mode, 'private': False},
            'metadata': {'imagePrompts': 0},
            't': 'imagine',
            'prompt': prompt
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, json=payload, headers=self.common_headers) as response:
                print(await response.text())
                if response.status == 200:
                    data = await response.json()
                    if 'success' in data and data['success']:
                        return data['success'][0]['job_id']
                raise Exception('Ошибка генерации изображения')

    def get_image(self, task_id, index, max_attempts=10, timeout=120):
        image_url = f"{self.cdn_url}/{task_id}/0_{index}.png"
        
        attempts = 0
        start_time = time.time()
        
        while attempts < max_attempts:
            try:
                response = scraper.get(image_url, headers=self.get_image_headers, stream=True, timeout=timeout)
                print(response)
                
                if response.status_code == 200:
                    return response.content
                
                elif response.status_code == 404:
                    print(f"Изображение не найдено (404) для task_id: {task_id}, index: {index}. Продолжаем попытки...")
                
                else:
                    raise Exception(f"Ошибка при запросе изображения: код {response.status_code}")
            
            except Exception as e:
                print(f"Попытка {attempts + 1}/{max_attempts} завершилась ошибкой: {e}")
            
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Превышен лимит времени ожидания {timeout} секунд для получения изображения.")
            
            attempts += 1
            time.sleep(10)
        
        raise Exception(f"Не удалось получить изображение за {max_attempts} попыток.")

    async def submit_job(self, payload):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=self.common_headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'success' in data and data['success']:
                            return data['success'][0]['job_id']
                    print(f"midjourney | submit_job | Error {response.status}")
                    raise Exception(f"submit_job failed with status code {response.status}")
        except Exception as e:
            print(f"midjourney | submit_job | Exception: {e}")
            raise

    async def vary(self, task_id, index, mode):
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "metadata": {"imagePrompts": None, "imageReferences": None, "characterReferences": None},
                "t": "vary",
                "strong": True,
                "id": task_id,
                "index": index
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | vary | Exception: {e}")
            raise

    async def upscale(self, task_id, index, mode):
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "metadata": {"imagePrompts": None, "imageReferences": None, "characterReferences": None},
                "t": "upscale",
                "type": "v6r1_2x_creative",
                "id": task_id,
                "index": index
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | upscale | Exception: {e}")
            raise

    async def remix(self, images, mode, new_prompt=None):
        prompt = ''.join(images)
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "roomId": None,
                "metadata": {"imagePrompts": len(images), "imageReferences": 0, "characterReferences": 0},
                "t": "imagine",
                "prompt": f"{prompt} {new_prompt if new_prompt else ''} --v 6.1"
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | remix | Exception: {e}")
            raise


    async def pan(self, task_id, index, direction, mode):
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "metadata": {"imagePrompts": None, "imageReferences": None, "characterReferences": None},
                "t": "pan",
                "newPrompt": None,
                "direction": direction,
                "fraction": 0.5,
                "stitch": True,
                "id": task_id,
                "index": index
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | pan | Exception: {e}")
            raise

    async def zoom(self, task_id, index, zoom_factor, mode):
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "metadata": {"imagePrompts": None, "imageReferences": None, "characterReferences": None},
                "t": "outpaint",
                "newPrompt": None,
                "zoomFactor": zoom_factor,
                "id": task_id,
                "index": index
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | zoom | Exception: {e}")
            raise

    async def rerun(self, task_id, mode):
        try:
            payload = {
                "f": {"mode": mode, "private": False},
                "channelId": "singleplayer_185f84ec-3edd-48a3-a0a1-4aa471fdb7f9",
                "metadata": {"imagePrompts": None, "imageReferences": None, "characterReferences": None},
                "t": "reroll",
                "newPrompt": None,
                "id": task_id
            }
            return await self.submit_job(payload)
        except Exception as e:
            print(f"midjourney | rerun | Exception: {e}")
            raise

    def save_image_to_file(self, task_id, index, output_path="output/midjourneyTasks"):
        image_bytes = self.get_image(task_id, index)
        os.makedirs(output_path, exist_ok=True)
        file_path = os.path.join(output_path, f"{task_id}_{index}.png")
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        return file_path

    async def save_images_in_thread(self, task_id, output_path="output/midjourneyTasks", one_file=False):
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            if one_file:
                await loop.run_in_executor(pool, self.save_image_to_file, task_id, 0, output_path)
            else:
                for index in range(4):
                    await loop.run_in_executor(pool, self.save_image_to_file, task_id, index, output_path)
                    