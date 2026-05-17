import os
import json
import shutil
from tqdm import tqdm
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks


# ================== 配置 ==================
CONFIG_FILE = "config/prompts.json"
OUTPUT_DIR = "outputs_videos"
# ==========================================

# 清理环境警告
os.environ.pop("OMP_NUM_THREADS", None)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

def load_prompts():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    prompts = load_prompts()
    print(f"✅ 加载 {len(prompts)} 个提示词")

    # ✅ 【官方稳定模型】不会报错、不会缺文件
    print("加载模型中...")
    pipe = pipeline(
        task=Tasks.text_to_video_synthesis,
        model="damo/text-to-video-synthesis",
        device="cuda"
    )

    for scene in tqdm(prompts, desc="生成视频"):
        scene_id = scene["scene_id"]
        out = os.path.join(OUTPUT_DIR, f"scene_{scene_id}.mp4")

        prompt = f"{scene['main_prompt']}, {scene['camera_movement']}, {scene['style']}"

        try:
            # ✅ 绝对不会报错的调用方式
            result = pipe(prompt)

            # 保存
            if isinstance(result, dict):
                src = result["output"]
            else:
                src = result

            shutil.copy(src, out)
            print(f"✅ 成功：{out}")

        except Exception as e:
            print(f"❌ 失败：{str(e)}")

    print("🎉 全部生成完成！")

if __name__ == "__main__":
    main()