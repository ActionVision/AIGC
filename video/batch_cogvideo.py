import os
import json
import torch
from tqdm import tqdm
from diffusers import PixArtTransformer2DModel, TextToVideoSDPipeline
from diffusers.utils import export_to_video

# ========== 清理环境报错 ==========
os.environ.pop("OMP_NUM_THREADS", None)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ========== 配置 ==========
CONFIG_FILE = "config/prompts.json"
OUTPUT_DIR = "outputs_final"
DEVICE = "cuda"
# ==========================

os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_prompts():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    prompts = load_prompts()
    print(f"✅ 加载 {len(prompts)} 个提示词")

    print("\n加载轻量视频模型（不占空间、秒加载）...")

    # ✅ 轻量模型，不会下载几十G，不会网络失败
    pipe = TextToVideoSDPipeline.from_pretrained(
        "cerspense/zeroscope_v2_576w",
        torch_dtype=torch.float16
    ).to(DEVICE)

    pipe.enable_vae_slicing()

    # 批量生成
    for scene in tqdm(prompts, desc="生成视频"):
        sid = scene["scene_id"]
        prompt = f"{scene['main_prompt']}, {scene['camera_movement']}, {scene['style']}"
        out = os.path.join(OUTPUT_DIR, f"scene_{sid}.mp4")

        try:
            video = pipe(
                prompt=prompt,
                num_frames=16,
                width=576,
                height=320,
                num_inference_steps=25,
            ).frames[0]

            export_to_video(video, out, fps=8)
            tqdm.write(f"✅ 成功：{out}")

        except Exception as e:
            tqdm.write(f"❌ 失败：{str(e)}")

    print("\n🎉 全部生成完成！")

if __name__ == "__main__":
    main()