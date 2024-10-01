import os
import asyncio
import aiohttp
from pathlib import Path
from tasks import suno_tasks

class SunoCore:
    def __init__(self, session_id, cookie):
        self.api_url = 'https://studio-api.suno.ai/api/generate/v2/'
        self.feed_api_url = 'https://studio-api.suno.ai/api/feed/?ids='
        self.session_id = session_id
        self.cookie = cookie
        self.token = None
        self.cookies = cookie
        self.common_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Referer': 'https://suno.com',
            'Origin': 'https://suno.com'
        }

    async def get_clip_ids(self, gpt_description_prompt, make_instrumental):
        payload = {
            "gpt_description_prompt": gpt_description_prompt,
            "mv": "chirp-v3-5",
            "prompt": "",
            "make_instrumental": make_instrumental,
            "user_uploaded_images_b64": [],
            "generation_type": "TEXT"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, json=payload, headers={
                'Authorization': self.token,
                'Content-Type': 'application/json',
                'Cookie': self.cookies,
                **self.common_headers
            }) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'clips' in data:
                        clip_ids = [clip['id'] for clip in data['clips']]
                        return clip_ids[:2]
                elif response.status == 401:
                    await self.refresh_token()
                    return await self.get_clip_ids(gpt_description_prompt, make_instrumental)
                else:
                    raise Exception(f'suno | get_clip_ids |  response: {response.status}')

    async def download_mp3(self, clip_id, output_path="output/sunoTasks"):
        audio_url = await self.get_audio_url(clip_id)
        if not audio_url:
            return

        Path(output_path).mkdir(parents=True, exist_ok=True)
        file_path = Path(output_path) / f"{clip_id}.mp3"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url, headers={
                    'Cookie': self.cookies,
                    **self.common_headers
                }) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                    else:
                        print(f"suno | download_mp3 | response: {response.status}")
                        raise Exception('Не удалось скачать песню')
        except Exception as e:
            print(f"suno | download_mp3 | {e}")

    async def get_audio_url(self, clip_id):
        while True:
            try:
                feed_data = await self.get_feed(clip_id)
                
                if feed_data:
                    status = feed_data[0].get('status', '')
                    
                    if status == 'complete' and feed_data[0].get('audio_url'):
                        return feed_data[0]['audio_url']
                    elif status == 'error':
                        suno_tasks[clip_id] = 'error'
                    else:
                        print(f"suno | {clip_id}: {status}")
                
            except Exception as e:
                print(f"suno | get_audio_url | {e}")

            await asyncio.sleep(15)

    async def get_feed(self, clip_id):
        if self.token is None:
            await self.refresh_token()

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.feed_api_url}{clip_id}", headers={
                'Authorization': self.token,
                'Cookie': self.cookies,
                **self.common_headers
            }) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    print(f"suno | get_feed | {response.status}... Refreshing token.")
                    await self.refresh_token()
                    return await self.get_feed(clip_id)
                elif response.status == 404:
                    print(f"suno | get_feed | {response.status}... Waiting 10 sec...")
                    await asyncio.sleep(10)
                else:
                    print(f"suno | get_feed | {response.status} exception")
                    raise Exception(f"suno | get_feed | {response.status} exception")

    async def refresh_token(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f'https://clerk.suno.com/v1/client/sessions/{self.session_id}/tokens?_clerk_js_version=5.17.0',
                        headers={
                            'Cookie': self.cookies,
                            'Content-Type': 'application/json',
                            **self.common_headers
                        }) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = f"Bearer {data['jwt']}"
                        print(f"suno | refresh_token | {response.status} OK")
                    else:
                        raise Exception(f"suno | refresh_token | {response.status} ERROR")
        except Exception as e:
            print(f"suno | refresh_token | {e}")
            raise

    async def keep_token_alive(self):
        while True:
            try:
                await self.refresh_token()
                await asyncio.sleep(60)
            except Exception as e:
                print(f"suno | keep_token_alive | {e}")
                await asyncio.sleep(60)

