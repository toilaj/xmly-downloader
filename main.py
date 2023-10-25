import http
import sys
import asyncio
import requests
import aiohttp
import traceback
import fake_useragent
import json
import aiofiles
import os
from alive_progress import alive_bar

OUTPUT_DIR = "output"
ALBUM_TRACK_LIST_URL = "https://www.ximalaya.com/revision/album/v1/getTracksList"
ALBUM_TRACK_GET_URL = "http://mobile.ximalaya.com/v1/track/baseInfo"
PAGE_SIZE = 30
HEADERS = {"user-agent": fake_useragent.UserAgent().chrome}


def get_album_info(id):
    response = requests.get(ALBUM_TRACK_LIST_URL, headers=HEADERS, params={"albumId": id, "pageNum": 0, "pageSize": 1})
    if response.status_code == http.HTTPStatus.OK:
        info = response.json()
        return info["data"]
    else:
        return None


async def get_track_id_by_page(album_id, page):
    async with aiohttp.ClientSession() as session:
        async with session.get(ALBUM_TRACK_LIST_URL, headers=HEADERS,
                               params={"albumId": album_id, "pageNum": page, "pageSize": PAGE_SIZE}) as response:
            if response.status == http.HTTPStatus.OK:
                r = json.loads(await response.text())
                return r['data']['tracks']
            else:
                print(response.status)
                return None


async def get_track_ids(info):
    count = info["trackTotalCount"]
    id = info["albumId"]
    page_count = round(count / PAGE_SIZE + 0.4)
    tasks = []
    track_ids = []
    tracks = []
    async with asyncio.TaskGroup() as tg:
        for i in range(page_count):
            tasks.append(tg.create_task(get_track_id_by_page(id, i)))
    for task in tasks:
        tracks.extend(task.result())
    for track in tracks:
        track_ids.append(track["trackId"])
    return track_ids


async def get_track_metadata(track_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(ALBUM_TRACK_GET_URL, headers=HEADERS,
                               params={"device": "iPhone", "trackId": track_id}) as response:
            r = await response.json()
            return {"title": r["title"], "url": r["playUrl64"]}


async def get_album_tracks_metadatas(info):
    track_ids = await get_track_ids(info)
    tasks = []
    metadatas = []
    async with asyncio.TaskGroup() as tg:
        for track_id in track_ids:
            tasks.append(tg.create_task(get_track_metadata(track_id)))
    for task in tasks:
        metadatas.append(task.result())
    return metadatas


async def download_track(out_dir, metadata_list, finish):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=len(metadata_list) * 300)) as session:
        for metadata in metadata_list:
            file = os.path.join(out_dir, metadata["title"] + ".mp3")
            async with session.get(metadata["url"], headers=HEADERS) as response:
                if response.status == http.HTTPStatus.OK:
                    async with aiofiles.open(file, "wb") as f:
                        await f.write(await response.read())
                else:
                    print("download track error:" + str(response.status))
                finish()


async def get_tracks(info):
    metadata_list = await get_album_tracks_metadatas(info)
    album_title = info["tracks"][0]["albumTitle"]
    out_dir = os.path.join(OUTPUT_DIR, album_title)
    os.mkdir(out_dir)
    with alive_bar(len(metadata_list), bar='blocks', title=album_title) as bar:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(download_track(out_dir, metadata_list, bar))


def main(album_ids):
    try:
        for album_id in album_ids:
            info = get_album_info(album_id)
            if info is None:
                print("Cannot get album info for ", album_id)
                return
            asyncio.run(get_tracks(info))
    except:
        print(traceback.format_exc())


def check_id(ids):
    for album_id in ids:
        if not album_id.isdigit():
            print("id: %s is not valid album id" % album_id)
            return False
    return True


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("input album id split by \",\", ex: 100000,1100200")
        ids = [id.strip() for id in input("IDs: ").split(",")]
        if not check_id(ids):
            exit(1)
        if not os.path.exists(OUTPUT_DIR):
            os.mkdir(OUTPUT_DIR)
        main(ids)
    else:
        print("Parameters error.")
