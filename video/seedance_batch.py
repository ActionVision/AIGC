#!/usr/bin/env python3
"""
Seedance 2.0 批量视频生成脚本
Volcengine ARK 平台 · doubao-seedance-2-0-260128

用法:
  python seedance_batch.py                        # 使用内置任务列表
  python seedance_batch.py --tasks tasks.csv      # 从 CSV 文件加载任务
  python seedance_batch.py --tasks tasks.json     # 从 JSON 文件加载任务
  python seedance_batch.py --concurrency 3        # 同时运行最多 3 个任务
  python seedance_batch.py --no-download          # 只提交任务，不下载视频
"""

import os
import sys
import csv
import json
import time
import argparse
import logging
import requests
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─────────────────────────── 配置区 ───────────────────────────
API_KEY   = "ark-21d920ea-98a0-48d6-8543-1e9c856843f8-a5c4f"   # 你的 ARK API Key
BASE_URL  = "https://ark.cn-beijing.volces.com/api/v3"
MODEL_STD = "doubao-seedance-2-0-260128"        # 标准模型（质量更高）
MODEL_FAST= "doubao-seedance-2-0-fast-260128"   # 快速模型（速度更快）

OUTPUT_DIR  = Path("videos")          # 视频保存目录
STATE_FILE  = Path("batch_state.json") # 断点续跑状态文件
LOG_FILE    = Path("seedance_batch.log")

# 并发 & 重试参数
MAX_CONCURRENCY = 2     # 同时提交任务数（建议 ≤ 3，防止超配额）
MAX_POLL_WAIT   = 600   # 最大等待秒数（10 分钟）
POLL_INIT_WAIT  = 10    # 首次轮询等待秒数
POLL_MAX_WAIT   = 60    # 轮询间隔上限
MAX_RETRIES     = 3     # 任务失败时最大重试次数
DOWNLOAD_TIMEOUT= 120   # 下载超时秒数

# ────────────────────────── 日志配置 ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("seedance")

# ─────────────────────────── 数据结构 ──────────────────────────
@dataclass
class VideoTask:
    """单个视频生成任务"""
    task_id: str                   # 自定义任务 ID（用于文件命名）
    prompt: str                    # 文字提示词
    resolution: str  = "1080p"    # 分辨率: 480p / 720p / 1080p / 2k
    ratio: str       = "16:9"     # 宽高比: 16:9 / 9:16 / 1:1 / 4:3 / 21:9 / adaptive
    duration: int    = 5          # 视频时长（秒）: 5 / 10 / 15
    model: str       = MODEL_STD  # 模型选择
    image_url: str   = ""         # 图生视频时的首帧图片 URL（可选）
    last_image_url: str = ""      # 首尾帧控制的末帧图片 URL（可选）
    audio_url: str   = ""         # 参考音频 URL（可选）
    watermark: bool  = False      # 是否加水印
    # 运行时状态（不写入 CSV）
    ark_task_id: str = ""         # ARK 返回的任务 ID
    status: str      = "pending"  # pending / submitted / succeeded / failed / skipped
    video_path: str  = ""         # 本地保存路径
    error: str       = ""         # 失败原因
    attempts: int    = 0          # 已尝试次数


@dataclass
class BatchState:
    """断点续跑状态"""
    tasks: dict = field(default_factory=dict)  # task_id -> task dict


# ─────────────────────────── HTTP 工具 ────────────────────────
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

def _post(endpoint: str, payload: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()

def _get(endpoint: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────── 核心逻辑 ─────────────────────────

def build_content(task: VideoTask) -> list:
    """构建 content 数组（支持文本、图片、音频多模态输入）"""
    content = [{"type": "text", "text": task.prompt}]
    if task.image_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": task.image_url}
        })
    if task.last_image_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": task.last_image_url, "use_as": "last_frame"}
        })
    if task.audio_url:
        content.append({
            "type": "audio_url",
            "audio_url": {"url": task.audio_url}
        })
    return content


def submit_task(task: VideoTask) -> str:
    """提交视频生成任务，返回 ARK task_id"""
    payload = {
        "model": task.model,
        "content": build_content(task),
        "resolution": task.resolution,
        "ratio": task.ratio,
        "duration": task.duration,
        "watermark": task.watermark,
    }
    data = _post("/contents/generations/tasks", payload)
    return data["id"]


def poll_task(ark_task_id: str) -> dict:
    """轮询直到任务完成，返回最终响应 dict"""
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
            raise RuntimeError(f"任务终止，状态: {status}，详情: {data.get('error', '')}")
        wait = min(wait * 1.5, POLL_MAX_WAIT)
    raise TimeoutError(f"超时（{MAX_POLL_WAIT}s），任务 {ark_task_id} 仍未完成")


def download_video(url: str, save_path: Path) -> None:
    """流式下载视频文件"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def process_task(task: VideoTask, download: bool, state: BatchState, lock: threading.Lock) -> VideoTask:
    """完整处理一个任务：提交 → 轮询 → 下载"""
    log.info(f"[{task.task_id}] ▶  开始处理 | prompt: {task.prompt[:60]}…")

    for attempt in range(1, MAX_RETRIES + 1):
        task.attempts = attempt
        try:
            # 提交
            if not task.ark_task_id:
                task.ark_task_id = submit_task(task)
                task.status = "submitted"
                log.info(f"[{task.task_id}] ✅ 已提交 ark_id={task.ark_task_id}")
                _save_state(state, task, lock)

            # 轮询
            result = poll_task(task.ark_task_id)
            video_url = result["content"]["video_url"]
            log.info(f"[{task.task_id}] 🎬 生成完成，URL: {video_url[:60]}…")

            # 下载
            if download:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = OUTPUT_DIR / f"{task.task_id}_{ts}.mp4"
                download_video(video_url, save_path)
                task.video_path = str(save_path)
                log.info(f"[{task.task_id}] 💾 已保存: {save_path}")

            task.status = "succeeded"
            _save_state(state, task, lock)
            return task

        except Exception as e:
            task.error = str(e)
            log.warning(f"[{task.task_id}] ⚠️  第 {attempt}/{MAX_RETRIES} 次失败: {e}")
            if attempt < MAX_RETRIES:
                # 提交失败时清空 ark_id，下次重新提交
                if task.status != "submitted":
                    task.ark_task_id = ""
                time.sleep(5 * attempt)
            else:
                task.status = "failed"
                log.error(f"[{task.task_id}] ❌ 最终失败: {e}")
                _save_state(state, task, lock)

    return task


# ───────────────────────── 状态持久化 ──────────────────────────

def _save_state(state: BatchState, task: VideoTask, lock: threading.Lock):
    with lock:
        state.tasks[task.task_id] = asdict(task)
        STATE_FILE.write_text(json.dumps(state.tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> BatchState:
    s = BatchState()
    if STATE_FILE.exists():
        try:
            s.tasks = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            log.info(f"📂 加载断点状态：{len(s.tasks)} 条记录")
        except Exception:
            pass
    return s


# ─────────────────────────── 任务加载 ─────────────────────────

def load_tasks_csv(path: str) -> list[VideoTask]:
    """
    CSV 格式（UTF-8 with BOM 或无 BOM）：
    task_id,prompt,resolution,ratio,duration,model,image_url,last_image_url,audio_url,watermark
    """
    tasks = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = VideoTask(
                task_id     = row.get("task_id", f"task_{len(tasks)+1:04d}"),
                prompt      = row.get("prompt", ""),
                resolution  = row.get("resolution", "1080p"),
                ratio       = row.get("ratio", "16:9"),
                duration    = int(row.get("duration", 5)),
                model       = row.get("model", MODEL_STD),
                image_url   = row.get("image_url", ""),
                last_image_url = row.get("last_image_url", ""),
                audio_url   = row.get("audio_url", ""),
                watermark   = row.get("watermark", "false").lower() == "true",
            )
            tasks.append(t)
    return tasks


def load_tasks_json(path: str) -> list[VideoTask]:
    """
    JSON 格式：列表，每项对应 VideoTask 字段
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = []
    for i, item in enumerate(data):
        t = VideoTask(
            task_id     = item.get("task_id", f"task_{i+1:04d}"),
            prompt      = item.get("prompt", ""),
            resolution  = item.get("resolution", "1080p"),
            ratio       = item.get("ratio", "16:9"),
            duration    = int(item.get("duration", 5)),
            model       = item.get("model", MODEL_STD),
            image_url   = item.get("image_url", ""),
            last_image_url = item.get("last_image_url", ""),
            audio_url   = item.get("audio_url", ""),
            watermark   = item.get("watermark", False),
        )
        tasks.append(t)
    return tasks


def default_task_list() -> list[VideoTask]:
    """内置示例任务列表（没有提供文件时使用）"""
    return [
        VideoTask(
            task_id="001_nature",
            prompt="A serene mountain lake at golden hour, mist rising from the water, "
                   "cinematic wide shot, slow dolly forward, 8K hyperrealistic",
            resolution="1080p", ratio="16:9", duration=5,
        ),
        VideoTask(
            task_id="002_city",
            prompt="Futuristic cyberpunk city at night, neon reflections on wet streets, "
                   "aerial crane shot descending, volumetric fog",
            resolution="1080p", ratio="16:9", duration=5,
        ),
        VideoTask(
            task_id="003_portrait",
            prompt="Close-up portrait of an elderly craftsman working on intricate wooden carvings, "
                   "soft studio lighting, subtle camera push-in",
            resolution="720p", ratio="9:16", duration=5,
        ),
        VideoTask(
            task_id="004_product",
            prompt="Luxury perfume bottle rotating slowly on a black velvet surface, "
                   "dramatic side lighting, macro lens, particle dust floating",
            resolution="1080p", ratio="1:1", duration=5,
            model=MODEL_FAST,  # 产品演示用快速模型节省成本
        ),
        VideoTask(
            task_id="005_ocean",
            prompt="Underwater coral reef teeming with colorful fish, diver swimming through, "
                   "sunlight rays piercing the surface, slow motion",
            resolution="2k", ratio="16:9", duration=10,
        ),
    ]


# ─────────────────────────── 报告输出 ──────────────────────────

def print_report(tasks: list[VideoTask]):
    succeeded = [t for t in tasks if t.status == "succeeded"]
    failed    = [t for t in tasks if t.status == "failed"]
    skipped   = [t for t in tasks if t.status == "skipped"]

    print("\n" + "═" * 60)
    print("  📊  批量任务执行报告")
    print("═" * 60)
    print(f"  总任务数   : {len(tasks)}")
    print(f"  ✅ 成功    : {len(succeeded)}")
    print(f"  ❌ 失败    : {len(failed)}")
    print(f"  ⏭️  跳过    : {len(skipped)}")
    print("─" * 60)

    if succeeded:
        print("\n  生成成功的视频：")
        for t in succeeded:
            path = t.video_path or "（未下载）"
            print(f"    [{t.task_id}] {path}")

    if failed:
        print("\n  失败任务详情：")
        for t in failed:
            print(f"    [{t.task_id}] {t.error[:80]}")

    print("\n" + "═" * 60)
    print(f"  日志文件: {LOG_FILE.absolute()}")
    print(f"  状态文件: {STATE_FILE.absolute()}")
    if succeeded and tasks[0].video_path:
        print(f"  视频目录: {OUTPUT_DIR.absolute()}")
    print("═" * 60 + "\n")


def save_report_csv(tasks: list[VideoTask]):
    """将结果保存为 CSV，方便后续分析"""
    report_path = Path("batch_report.csv")
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        fields = ["task_id", "status", "ark_task_id", "video_path", "attempts", "error", "prompt"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in tasks:
            writer.writerow({k: getattr(t, k) for k in fields})
    log.info(f"📄 结果已写入: {report_path}")


# ────────────────────────────── main ───────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seedance 2.0 批量视频生成")
    parser.add_argument("--tasks",       default=None,           help="任务文件路径（.csv 或 .json）")
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY, help="最大并发数（默认 2）")
    parser.add_argument("--model",       default=None,           help="覆盖所有任务的模型 ID")
    parser.add_argument("--resolution",  default=None,           help="覆盖所有任务的分辨率")
    parser.add_argument("--no-download", action="store_true",    help="只提交任务，不下载视频")
    parser.add_argument("--fresh",       action="store_true",    help="忽略断点状态，重新全量运行")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── 加载任务 ──
    if args.tasks:
        p = args.tasks.lower()
        if p.endswith(".csv"):
            tasks = load_tasks_csv(args.tasks)
        elif p.endswith(".json"):
            tasks = load_tasks_json(args.tasks)
        else:
            log.error("任务文件仅支持 .csv 或 .json 格式")
            sys.exit(1)
        log.info(f"📋 从 {args.tasks} 加载了 {len(tasks)} 个任务")
    else:
        tasks = default_task_list()
        log.info(f"📋 使用内置示例任务列表，共 {len(tasks)} 个")

    # ── 全局参数覆盖 ──
    for t in tasks:
        if args.model:      t.model = args.model
        if args.resolution: t.resolution = args.resolution

    # ── 断点续跑：恢复已完成的任务 ──
    state = BatchState() if args.fresh else load_state()
    for t in tasks:
        saved = state.tasks.get(t.task_id)
        if saved and saved.get("status") in ("succeeded",) and not args.fresh:
            t.status      = saved["status"]
            t.ark_task_id = saved.get("ark_task_id", "")
            t.video_path  = saved.get("video_path", "")
            t.attempts    = saved.get("attempts", 0)
            log.info(f"[{t.task_id}] ⏭️  已跳过（上次成功完成）")
        elif saved and saved.get("status") == "submitted" and saved.get("ark_task_id") and not args.fresh:
            # 上次提交成功但未轮询到结果，继续轮询
            t.ark_task_id = saved["ark_task_id"]
            t.status      = "submitted"
            log.info(f"[{t.task_id}] 🔄 恢复轮询 ark_id={t.ark_task_id}")

    pending = [t for t in tasks if t.status not in ("succeeded", "skipped")]
    log.info(f"🚀 待处理任务: {len(pending)} 个，并发数: {args.concurrency}")

    # ── 并发执行 ──
    lock = threading.Lock()
    download = not args.no_download

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(process_task, t, download, state, lock): t
            for t in pending
        }
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                t = futures[fut]
                log.error(f"[{t.task_id}] 线程异常: {e}")

    # ── 汇总报告 ──
    print_report(tasks)
    save_report_csv(tasks)


if __name__ == "__main__":
    main()