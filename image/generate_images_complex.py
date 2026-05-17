import os
import torch
from diffusers import StableDiffusionPipeline

# 设置镜像和缓存（如需）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HF_HOME'] = '/root/autodl-tmp/huggingface'

# 模型路径（可改用本地路径）
# MODEL_ID = "runwayml/stable-diffusion-v1-5"  # 或 SDXL: "stabilityai/stable-diffusion-xl-base-1.0"

# print("正在加载模型...")
# pipe = StableDiffusionPipeline.from_pretrained(
#     MODEL_ID,
#     torch_dtype=torch.float16,
#     safety_checker=None,  # 关闭安全检查（如不需要）
# )
pipe = StableDiffusionPipeline.from_pretrained("/root/autodl-tmp/stable-diffusion-v1-5")
pipe = pipe.to("cuda")
# 启用注意力切片节省显存（如果显存不足）
pipe.enable_attention_slicing()
# 可选：使用 VAE 提升细节（模型自带，无需额外设置）
# pipe.vae = pipe.vae.to(dtype=torch.float16)

# 通用负面提示词
NEGATIVE_PROMPT = (
    "worst quality, low quality, blurry, deformed, messy, ugly, "
    "bad anatomy, watermark, signature, text, extra limbs, fused fingers, "
    "monochrome, grayscale, oversaturated, cartoon, sketch, low resolution"
)

# 生成参数
NUM_INFERENCE_STEPS = 40    # 步数 30-50 足够
GUIDANCE_SCALE = 9.0        # 引导尺度 7-12

def generate_image(prompt: str, output_path: str) -> bool:
    try:
        with torch.autocast("cuda"):
            image = pipe(
                prompt,
                negative_prompt=NEGATIVE_PROMPT,
                num_inference_steps=NUM_INFERENCE_STEPS,
                guidance_scale=GUIDANCE_SCALE,
            ).images[0]
        image.save(output_path, quality=95)
        return True
    except Exception as e:
        print(f"生成失败: {e}")
        return False

def main():
    config_file = "config/prompts_complex.txt"
    output_dir = "/root/autodl-tmp/outputs_complex"
    
    if not os.path.exists(config_file):
        print(f"错误：找不到配置文件 {config_file}，请先运行 generate_complex_prompts.py")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(config_file, "r", encoding="utf-8") as f:
        prompts = [line.strip() for line in f if line.strip()]
    
    # 测试模式：先只生成前5张，确认效果后再去注释
    # prompts = prompts[:5]
    
    print(f"共加载 {len(prompts)} 条复杂提示词，开始生成高质量图片...")
    print(f"参数：steps={NUM_INFERENCE_STEPS}, guidance_scale={GUIDANCE_SCALE}")
    
    for idx, prompt in enumerate(prompts, 1):
        filename = f"{idx:04d}.png"
        output_path = os.path.join(output_dir, filename)
        print(f"[{idx}/{len(prompts)}] {prompt[:80]}...")
        success = generate_image(prompt, output_path)
        if not success:
            print(f"  失败！跳过")
    print("全部完成！")

if __name__ == "__main__":
    main()