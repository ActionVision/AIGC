import os
import json
import shutil
from tqdm import tqdm
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks

# ===================== 配置区 ======================
CONFIG_FILE = "config/prompts.json"
OUTPUT_DIR = "outputs_videos"
# ===================================================

# 环境修复（解决你环境的各种警告）
os.environ.pop("OMP_NUM_THREADS", None)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

def load_prompts():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    prompts = load_prompts()
    print(f"✅ 成功加载 {len(prompts)} 个镜头")

    print("\n正在加载模型...")
    pipe = pipeline(
        task=Tasks.text_to_video_synthesis,
        model="damo/text-to-video-synthesis",
        device="cuda"
    )
    print("✅ 模型加载完成！")

    for scene in tqdm(prompts, desc="生成进度"):
        scene_id = scene["scene_id"]
        save_path = os.path.join(OUTPUT_DIR, f"scene_{scene_id}.mp4")
        prompt = f"{scene['main_prompt']}, {scene['camera_movement']}, {scene['style']}"

        try:
            result = pipe(prompt)
            print(f"\n[DEBUG] scene {scene_id} 返回类型: {type(result)}")
            # 可选：打印前200字符避免过长
            print(f"[DEBUG] 返回值预览: {str(result)[:200]}")

            # ---------- 万能提取视频路径 ----------
            video_file = None

            if isinstance(result, dict):
                video_file = result.get("output") or result.get("video") or result.get("result") or result.get("file")
                if not video_file:
                    for v in result.values():
                        if isinstance(v, str) and v.endswith(('.mp4', '.avi', '.mov')):
                            video_file = v
                            break

            elif isinstance(result, str):
                if result.endswith('.mp4'):
                    video_file = result
                else:
                    try:
                        data = json.loads(result)
                        if isinstance(data, dict):
                            video_file = data.get("output") or data.get("video")
                    except:
                        pass

            elif isinstance(result, list) and len(result) > 0:
                first = result[0]
                if isinstance(first, dict):
                    video_file = first.get("output") or first.get("video")
                elif isinstance(first, str) and first.endswith('.mp4'):
                    video_file = first

            if not video_file and isinstance(result, (str, bytes, os.PathLike)):
                video_file = str(result)

            # ---------- 保存 ----------
            if video_file and os.path.exists(video_file):
                shutil.copy(video_file, save_path)
                print(f"✅ 成功：{save_path}")
            else:
                print(f"⚠️ 未找到视频文件，原始返回：{result}")

        except Exception as e:
            print(f"❌ 失败：{str(e)}")
            import traceback
            traceback.print_exc()

    print("\n🎉 全部生成完成！")

if __name__ == "__main__":
    main()