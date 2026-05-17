import json
import time
import requests

# ==================== 配置 ====================
YOUR_API_KEY = "mCMsT68ww6GhN5waRo2Cmb82ODt5C4CmQWOtPtvw99g94ocm"  # 替换成你的 AutoDL API Key
YOUR_ENDPOINT = "https://api.autodl.com/v1/video/generate"  # 官方视频生成接口
PROMPT_FILE = "config/prompts.json"
OUTPUT_FILE = "video_results.json"
# ==============================================

def load_prompts():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_video(prompt):
    headers = {
        "Authorization": f"Bearer {YOUR_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "prompt": prompt,
        "width": 720,
        "height": 480,
        "fps": 16,
        "steps": 30,
        "model": "text-to-video"
    }

    # 发送生成请求
    resp = requests.post(YOUR_ENDPOINT, json=data, headers=headers)
    result = resp.json()

    if result.get("code") != 0:
        return None, f"错误：{result}"

    task_id = result["data"]["task_id"]
    return task_id, None

def get_result(task_id):
    headers = {"Authorization": f"Bearer {YOUR_API_KEY}"}
    url = f"https://api.autodl.com/v1/video/result?task_id={task_id}"

    while True:
        resp = requests.get(url, headers=headers)
        data = resp.json()

        if data["data"]["status"] == "completed":
            return data["data"]["video_url"]
        if data["data"]["status"] == "failed":
            return None
        time.sleep(5)

def main():
    prompts = load_prompts()
    results = []

    for idx, scene in enumerate(prompts):
        scene_id = scene["scene_id"]
        prompt = f"{scene['main_prompt']}, {scene['camera_movement']}, {scene['style']}"
        print(f"[{idx+1}/{len(prompts)}] 生成：{prompt[:50]}...")

        task_id, err = generate_video(prompt)
        if err:
            print(err)
            continue

        video_url = get_result(task_id)
        if video_url:
            print(f"✅ 成功：{video_url}")
            results.append({
                "scene_id": scene_id,
                "prompt": prompt,
                "video_url": video_url
            })
        else:
            print("❌ 生成失败")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 全部完成！结果已保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()