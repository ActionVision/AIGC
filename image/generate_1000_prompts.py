import random
import os

# ----- 词汇库（可随意扩充）-----
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

# ----- 生成 1000 条提示词 -----
def generate_prompt():
    subject = random.choice(subjects)
    style = random.choice(styles)
    color = random.choice(colors)
    action = random.choice(actions)
    # 随机组合，也可加入“with a [something]”等结构
    templates = [
        f"{subject} in {style}, {color} tones, {action}",
        f"A {color} {subject} {action}, {style}",
        f"{style} of {subject}, {color} atmosphere, {action}",
        f"{subject} {action} in a {color} world, {style}"
    ]
    return random.choice(templates)

def main():
    os.makedirs("config", exist_ok=True)
    output_file = "config/prompts.txt"
    num_prompts = 10000

    with open(output_file, "w", encoding="utf-8") as f:
        for i in range(num_prompts):
            prompt = generate_prompt()
            f.write(prompt + "\n")

    print(f"已生成 {num_prompts} 条提示词，保存至 {output_file}")

if __name__ == "__main__":
    main()