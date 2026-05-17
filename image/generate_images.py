import os
import torch
from diffusers import StableDiffusionPipeline

# 1. 设置镜像站（关键！）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
# 2. 设置缓存目录到数据盘（避免占满系统盘）
os.environ['HF_HOME'] = '/root/autodl-tmp/huggingface'

# 3. 全局加载模型（只执行一次）
print("正在加载模型，首次运行需要下载约2GB文件，请耐心等待...")
# pipe = StableDiffusionPipeline.from_pretrained(
#     "runwayml/stable-diffusion-v1-5",
#     torch_dtype=torch.float16
# )
pipe = StableDiffusionPipeline.from_pretrained("/root/autodl-tmp/stable-diffusion-v1-5")
pipe = pipe.to("cuda")
# 可选：如果显存不足，取消下一行的注释
# pipe.enable_attention_slicing()
print("模型加载完成！")

def generate_image(prompt: str, output_path: str) -> bool:
    try:
        with torch.autocast("cuda"):
            image = pipe(prompt).images[0]
        image.save(output_path)
        return True
    except Exception as e:
        print(f"生成失败: {e}")
        return False

def main():
    config_file = "config/prompts.txt"
    output_dir = "/root/autodl-tmp/outputs"

    if not os.path.exists(config_file):
        print(f"错误：找不到配置文件 {config_file}")
        return

    os.makedirs(output_dir, exist_ok=True)

    with open(config_file, "r", encoding="utf-8") as f:
        prompts = [line.strip() for line in f if line.strip()]

    # 建议先测试前10条，避免一次性生成1000条出问题
    # prompts = prompts[:10]   # 取消注释以测试

    print(f"共加载 {len(prompts)} 条提示词，开始生成...")
    for idx, prompt in enumerate(prompts, 1):
        filename = f"{idx:04d}.png"
        output_path = os.path.join(output_dir, filename)
        print(f"[{idx}/{len(prompts)}] {prompt[:60]}...")
        success = generate_image(prompt, output_path)
        if not success:
            print(f"  失败！跳过")
    print("全部完成！")

if __name__ == "__main__":
    main()