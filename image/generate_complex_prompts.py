import random
import os

# ----- 复杂度修饰词（前缀）-----
complexity_prefixes = [
    "highly detailed, intricate, complex composition,",
    "masterpiece, ultra high-res, 8K, intricate details,",
    "maximalist, rich textures, complex lighting,", 
    "chaotic, densely packed, many elements,",
    "ornate, elaborate, sophisticated,",
    "cinematic, volumetric lighting, deep depth of field,",
    "hyperdetailed, macro shot, sharp focus,",
    "award-winning photograph, fine art, high contrast,",
    "concept art, trending on ArtStation, intricate patterns,",
    "extremely detailed, realistic, texture rich,"
]

# ----- 复杂度后缀（追加在提示词末尾）-----
complexity_suffixes = [
    ", extremely detailed, 8K, HDR",
    ", intricate details, professional lighting, high quality",
    ", complex background, many objects, rich colors",
    ", ultra detailed, sharp focus, high contrast",
    ", densely packed scene, no empty spaces, intricate"
]

# ----- 原有基础词汇库（与之前类似）-----
subjects = [
    "a cat", "a dog", "a bird", "a dragon", "a castle", "a spaceship",
    "a forest", "a city", "a mountain", "an ocean", "a robot", "a flower",
    "a car", "a book", "a clock", "a sword", "a gem", "a statue"
]

styles = [
    "oil painting", "watercolor", "sketch", "3D render", "pixel art",
    "photorealistic", "anime style", "cyberpunk", "fantasy", "minimalist",
    "impressionism", "surrealism", "cartoon", "vintage", "steampunk"
]

colors = [
    "red", "blue", "green", "golden", "silver", "dark", "vibrant", "pastel",
    "monochrome", "rainbow", "warm", "cold"
]

actions = [
    "sitting", "flying", "running", "sleeping", "exploding", "shining",
    "floating", "dancing", "melting", "growing"
]

def generate_base_prompt():
    subject = random.choice(subjects)
    style = random.choice(styles)
    color = random.choice(colors)
    action = random.choice(actions)
    templates = [
        f"{subject} in {style}, {color} tones, {action}",
        f"A {color} {subject} {action}, {style}",
        f"{style} of {subject}, {color} atmosphere, {action}",
        f"{subject} {action} in a {color} world, {style}"
    ]
    return random.choice(templates)

def generate_complex_prompt():
    base = generate_base_prompt()
    prefix = random.choice(complexity_prefixes)
    suffix = random.choice(complexity_suffixes)
    # 组合：前缀 + 基础提示词 + 后缀
    return f"{prefix} {base}{suffix}"

def main():
    os.makedirs("config", exist_ok=True)
    num_prompts = 10000
    with open("config/prompts_complex.txt", "w", encoding="utf-8") as f:
        for _ in range(num_prompts):
            prompt = generate_complex_prompt()
            f.write(prompt + "\n")
    print(f"已生成 {num_prompts} 条复杂提示词，保存至 config/prompts_complex.txt")

if __name__ == "__main__":
    main()