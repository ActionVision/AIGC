#!/usr/bin/env python3
"""
多场景视频批量生成脚本
基于 talk_show_videos_1000.json，每个视频拆分为多场景分别生成后拼接

用法:
  python video_scene_generate.py                              # 处理全部 1000 个视频
  python video_scene_generate.py --start 0 --end 10           # 只处理前 10 个
  python video_scene_generate.py --video-ids 1,5,10,20        # 指定视频 ID
  python video_scene_generate.py --concurrency 3              # 最多 3 个场景并行
  python video_scene_generate.py --no-concat                  # 只生成场景，不拼接
  python video_scene_generate.py --fresh                      # 忽略断点状态重新跑
"""
import os
import sys
import json
import time
import shutil
import argparse
import logging
import requests
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional

# =========================== 配置区 ===========================
API_KEY   = "ark-21d920ea-98a0-48d6-8543-1e9c856843f8-a5c4f"
BASE_URL  = "https://ark.cn-beijing.volces.com/api/v3"
MODEL_STD = "doubao-seedance-2-0-260128"
MODEL_FAST= "doubao-seedance-2-0-fast-260128"

JSON_INPUT    = Path(__file__).parent / "talk_show_videos_1000.json"
SCENE_DIR     = Path("scene_videos")     # 场景片段保存目录
FINAL_DIR     = Path("final_videos")     # 拼接后最终视频目录
STATE_FILE    = Path("video_batch_state.json")
LOG_FILE      = Path("video_batch.log")

MAX_CONCURRENCY = 2
MAX_POLL_WAIT   = 600
POLL_INIT_WAIT  = 10
POLL_MAX_WAIT   = 60
MAX_RETRIES     = 3
DOWNLOAD_TIMEOUT= 120

# 场景 prompt 前缀模板：把镜头运动和风格注入
SCENE_PROMPT_TEMPLATE = "{camera}，{style}。{main_prompt}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("video_scene")

# =========================== 数据结构 ===========================

@dataclass
class SceneTask:
    """单个场景生成任务"""
    video_id: int
    scene_id: int
    prompt: str
    duration: int
    resolution: str = "1080p"
    ratio: str = "16:9"
    model: str = MODEL_STD
    # 运行时状态
    ark_task_id: str = ""
    status: str = "pending"
    video_path: str = ""
    error: str = ""
    attempts: int = 0

    @property
    def task_id(self) -> str:
        return f"v{self.video_id:04d}_s{self.scene_id:02d}"


@dataclass
class VideoJob:
    """一个完整视频（含多个场景）"""
    video_id: int
    scenes: list[SceneTask] = field(default_factory=list)
    concat_status: str = "pending"  # pending / concatting / done / failed


# =========================== HTTP 工具 ==========================

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

def _post(endpoint: str, payload: dict) -> dict:
    resp = requests.post(f"{BASE_URL}{endpoint}", json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()

def _get(endpoint: str) -> dict:
    resp = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()

# =========================== 核心逻辑 ===========================

def build_scene_prompt(scene: dict) -> str:
    """合并 camera_movement + style + main_prompt 为完整 prompt"""
    camera = scene.get("camera_movement", "")
    style = scene.get("style", "")
    main = scene.get("main_prompt", "")
    if camera and style:
        return f"{camera}，{style}。{main}"
    elif camera:
        return f"{camera}。{main}"
    elif style:
        return f"{style}。{main}"
    return main


def submit_scene(task: SceneTask) -> str:
    """提交单个场景生成任务"""
    payload = {
        "model": task.model,
        "content": [{"type": "text", "text": task.prompt}],
        "resolution": task.resolution,
        "ratio": task.ratio,
        "duration": task.duration,
        "watermark": False,
    }
    data = _post("/contents/generations/tasks", payload)
    return data["id"]


def poll_until_done(ark_task_id: str) -> dict:
    """轮询直到任务完成"""
    wait = POLL_INIT_WAIT
    elapsed = 0
    while elapsed < MAX_POLL_WAIT:
        time.sleep(wait)
        elapsed += wait
        data = _get(f"/contents/generations/tasks/{ark_task_id}")
        status = data.get("status", "")
        if status == "succeeded":
            return data
        elif status in ("failed", "expired", "cancelled"):
            raise RuntimeError(f"任务终止 ({status}): {data.get('error', '')}")
        wait = min(wait * 1.5, POLL_MAX_WAIT)
    raise TimeoutError(f"超时 ({MAX_POLL_WAIT}s)")


def download_video(url: str, save_path: Path) -> None:
    """流式下载"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def concat_videos(scene_paths: list[Path], output_path: Path) -> bool:
    """用 ffmpeg concat 拼接多个场景视频"""
    if not scene_paths:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 检查 ffmpeg 是否可用
    if not shutil.which("ffmpeg"):
        log.error("未找到 ffmpeg，请安装: sudo apt install ffmpeg")
        return False

    # 写 concat 文件列表
    concat_file = output_path.with_suffix(".txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in scene_paths:
            f.write(f"file '{p.absolute().as_posix()}'\n")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(output_path)],
            check=True, capture_output=True, timeout=300,
        )
        log.info(f"  拼接完成: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"  拼接失败: {e.stderr.decode()[:200] if e.stderr else e}")
        return False
    finally:
        concat_file.unlink(missing_ok=True)


def process_scene(task: SceneTask, lock: threading.Lock, states: dict) -> SceneTask:
    """处理单个场景: 提交 → 轮询 → 下载"""
    log.info(f"[{task.task_id}] ▶  scene {task.scene_id} | {task.duration}s | {task.prompt[:50]}…")

    for attempt in range(1, MAX_RETRIES + 1):
        task.attempts = attempt
        try:
            if not task.ark_task_id:
                task.ark_task_id = submit_scene(task)
                task.status = "submitted"
                log.info(f"[{task.task_id}] ✅ 已提交 ark={task.ark_task_id}")
                _save_scene_state(task, lock, states)

            result = poll_until_done(task.ark_task_id)
            video_url = result["content"]["video_url"]

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = SCENE_DIR / f"{task.task_id}_{ts}.mp4"
            download_video(video_url, save_path)
            task.video_path = str(save_path)
            task.status = "succeeded"
            log.info(f"[{task.task_id}] 💾 {save_path}")
            _save_scene_state(task, lock, states)
            return task

        except Exception as e:
            task.error = str(e)
            log.warning(f"[{task.task_id}] ⚠️  try {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                if task.status != "submitted":
                    task.ark_task_id = ""
                time.sleep(5 * attempt)
            else:
                task.status = "failed"
                log.error(f"[{task.task_id}] ❌ 最终失败")
                _save_scene_state(task, lock, states)
    return task


# =========================== JSON 加载 ===========================

def load_video_jobs(
    json_path: Path,
    start: int = 0,
    end: Optional[int] = None,
    video_ids: Optional[list[int]] = None,
) -> list[VideoJob]:
    """加载 JSON，解析为 VideoJob 列表"""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    jobs = []

    for video in data:
        vid = video["video_id"]

        if video_ids and vid not in video_ids:
            continue
        if vid < start:
            continue
        if end is not None and vid > end:
            continue

        scenes = []
        for s in video["scenes"]:
            full_prompt = build_scene_prompt(s)
            dur = s.get("duration_seconds", 5)
            # Seedance 支持的时长: 5/10/15，取最接近的
            if dur <= 7:
                gen_duration = 5
            elif dur <= 12:
                gen_duration = 10
            else:
                gen_duration = 15

            task = SceneTask(
                video_id=vid,
                scene_id=s["scene_id"],
                prompt=full_prompt,
                duration=gen_duration,
            )
            scenes.append(task)

        jobs.append(VideoJob(video_id=vid, scenes=scenes))

    total_scenes = sum(len(j.scenes) for j in jobs)
    log.info(f"📋 加载 {len(jobs)} 个视频, 共 {total_scenes} 个场景")
    return jobs


# =========================== 状态持久化 ===========================

def _save_scene_state(task: SceneTask, lock: threading.Lock, states: dict):
    with lock:
        states[task.task_id] = asdict(task)
        STATE_FILE.write_text(json.dumps(states, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def apply_state(jobs: list[VideoJob], states: dict, fresh: bool):
    """恢复断点状态"""
    if fresh or not states:
        return

    restored = 0
    for job in jobs:
        all_done = True
        for scene in job.scenes:
            saved = states.get(scene.task_id)
            if saved and saved.get("status") == "succeeded":
                scene.status = "succeeded"
                scene.video_path = saved.get("video_path", "")
                scene.ark_task_id = saved.get("ark_task_id", "")
                restored += 1
            elif saved and saved.get("status") == "submitted" and saved.get("ark_task_id"):
                scene.ark_task_id = saved["ark_task_id"]
                scene.status = "submitted"
                all_done = False
            else:
                all_done = False
        if all_done and all(s.status == "succeeded" for s in job.scenes):
            job.concat_status = "pending"  # 仍需拼接

    pending_scenes = sum(1 for j in jobs for s in j.scenes if s.status != "succeeded")
    log.info(f"📂 断点恢复: {restored} 个场景已完成, {pending_scenes} 个待处理")


# =========================== 报告 ===========================

def print_report(jobs: list[VideoJob]):
    all_scenes = [s for j in jobs for s in j.scenes]
    ok = sum(1 for s in all_scenes if s.status == "succeeded")
    fail = sum(1 for s in all_scenes if s.status == "failed")
    total = len(all_scenes)
    videos_done = sum(1 for j in jobs if j.concat_status == "done")

    print("\n" + "═" * 60)
    print("  📊  批量生成报告")
    print("═" * 60)
    print(f"  视频计划: {len(jobs)} 个")
    print(f"  场景总数: {total}")
    print(f"  ✅ 场景成功: {ok}")
    print(f"  ❌ 场景失败: {fail}")
    print(f"  ⏳ 场景待处理: {total - ok - fail}")
    print(f"  🎬 视频拼接完成: {videos_done}")
    print(f"  场景视频目录: {SCENE_DIR.absolute()}")
    print(f"  最终视频目录: {FINAL_DIR.absolute()}")
    print("═" * 60 + "\n")


# =========================== main ===========================

def main():
    parser = argparse.ArgumentParser(description="多场景视频批量生成")
    parser.add_argument("--start", type=int, default=0, help="起始 video_id")
    parser.add_argument("--end", type=int, default=None, help="结束 video_id")
    parser.add_argument("--video-ids", type=str, default=None, help="指定 video_id, 逗号分隔 (如 1,3,5)")
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY, help="场景并发数")
    parser.add_argument("--no-concat", action="store_true", help="只生成场景不拼接")
    parser.add_argument("--concat-only", action="store_true", help="只拼接已完成场景（不提交新任务）")
    parser.add_argument("--fresh", action="store_true", help="忽略断点状态")
    args = parser.parse_args()

    SCENE_DIR.mkdir(exist_ok=True)
    FINAL_DIR.mkdir(exist_ok=True)

    # 解析 video_ids
    video_ids = None
    if args.video_ids:
        video_ids = [int(x.strip()) for x in args.video_ids.split(",")]

    # 加载任务
    jobs = load_video_jobs(JSON_INPUT, start=args.start, end=args.end, video_ids=video_ids)

    # 断点恢复
    states = load_state()
    if not args.concat_only:
        apply_state(jobs, states, args.fresh)

    # 收集待处理场景
    pending_scenes = [s for j in jobs for s in j.scenes if s.status != "succeeded"]

    if not args.concat_only and pending_scenes:
        log.info(f"🚀 开始生成 {len(pending_scenes)} 个场景，并发数: {args.concurrency}")

        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(process_scene, s, lock, states): s for s in pending_scenes}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    s = futures[fut]
                    log.error(f"[{s.task_id}] 线程异常: {e}")

    # 拼接
    if not args.no_concat:
        concat_jobs = [j for j in jobs if j.concat_status != "done"]
        log.info(f"\n🎬 开始拼接 {len(concat_jobs)} 个视频…")

        for job in concat_jobs:
            scene_paths = []
            all_ready = True
            for s in sorted(job.scenes, key=lambda x: x.scene_id):
                if s.status == "succeeded" and s.video_path and Path(s.video_path).exists():
                    scene_paths.append(Path(s.video_path))
                else:
                    log.warning(f"[v{job.video_id:04d}] 场景 {s.scene_id} 未就绪，跳过拼接")
                    all_ready = False
                    break

            if all_ready and scene_paths:
                output = FINAL_DIR / f"talk_show_v{job.video_id:04d}.mp4"
                if concat_videos(scene_paths, output):
                    job.concat_status = "done"
                else:
                    job.concat_status = "failed"
            elif not scene_paths:
                log.warning(f"[v{job.video_id:04d}] 无可用场景视频")

    # 报告
    print_report(jobs)

    # 保存最终状态
    for job in jobs:
        for s in job.scenes:
            states[s.task_id] = asdict(s)
    STATE_FILE.write_text(json.dumps(states, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
