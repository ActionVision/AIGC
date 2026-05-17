import json
import random
from typing import List, Dict, Any

# 固定随机种子以便结果可重现（可选）
random.seed(42)

# 场景时长范围（秒）
DURATION_RANGE = (5, 15)  # 每个场景 5~15 秒
# 每个视频的场景数量范围
SCENES_PER_VIDEO_RANGE = (2, 5)

# 可选的摄像机运动方式
CAMERA_MOVEMENTS = [
    "固定镜头",
    "缓慢推拉",
    "环绕",
    "跟拍",
    "俯拍",
    "仰拍",
    "横移",
    "手持微晃",
    "变焦推进",
    "缓慢后退"
]

# 角色 ID 列表
CHARACTER_IDS = [
    "comedian_main",
    "comedian_female",
    "comedian_male",
    "audience_1",
    "audience_2",
    "host",
    "band_member",
    "guest_comedian"
]

# 风格描述
STYLES = [
    "专业脱口秀舞台、电影质感",
    "纪实风格、微光舞台",
    "高对比度、戏剧化灯光",
    "暖色调、亲密俱乐部氛围",
    "冷色调、大型剧院风格",
    "手持纪实、真实感",
    "复古胶片质感、单口喜剧专场"
]

# 脱口秀主题池（用于丰富提示词）
TOPICS = [
    "人工智能与日常生活",
    "职场内卷",
    "婚姻与恋爱",
    "社交媒体成瘾",
    "健身与自律",
    "父母与子女代沟",
    "租房与买房",
    "外卖与健康",
    "旅游踩坑经历",
    "科技产品吐槽",
    "宠物趣事",
    "童年回忆",
    "职场奇葩同事",
    "双十一购物节",
    "春节回家烦恼"
]

# 喜剧演员动作/状态
ACTIONS = [
    "手持麦克风，身体微微前倾",
    "双手比划，模仿夸张语气",
    "踱步舞台，与观众眼神交流",
    "突然停顿，制造冷场喜剧效果",
    "拿起水杯喝一口水，酝酿下一个梗",
    "坐在高脚凳上，放松地聊天",
    "用手指向观众席，互动提问",
    "模仿另一个角色，变换声调",
    "假装擦汗，表现紧张",
    "举起道具（如手机、书）辅助表演"
]

# 观众反应描述
AUDIENCE_REACTIONS = [
    "观众席爆发出笑声",
    "观众鼓掌喝彩",
    "有观众捂嘴大笑",
    "前排观众拍大腿笑",
    "观众集体吹口哨",
    "安静后突然爆笑",
    "观众发出‘哦——’的感叹",
    "零星笑声渐渐变大"
]

# 生成单个场景的提示词
def generate_main_prompt(scene_type: str, topic: str = None) -> str:
    if scene_type == "comedian":
        action = random.choice(ACTIONS)
        topic_str = random.choice(TOPICS) if topic is None else topic
        return f"一位{random.choice(['男', '女'])}脱口秀演员身穿{random.choice(['休闲西装','牛仔外套','印花T恤','衬衫+牛仔裤'])}，站在聚光灯下的舞台中央，{action}，正在讲一个关于“{topic_str}”的笑话。中景镜头，背景是深色幕布和麦克风支架。"
    elif scene_type == "audience":
        reaction = random.choice(AUDIENCE_REACTIONS)
        return f"观众席全景，{reaction}。有观众举起手机拍摄，有人笑得前仰后合。镜头扫过几张欢乐的面孔。"
    elif scene_type == "wide_stage":
        return f"广角镜头展示整个脱口秀俱乐部，舞台上一束追光打在演员身上，台下座无虚席，气氛热烈。酒吧式灯光，木质墙壁。"
    elif scene_type == "backstage":
        return f"后台准备区，演员对着镜子整理衣领，深呼吸，旁边有工作人员递水。暖色灯光，略带紧张感。"
    elif scene_type == "closeup":
        action = random.choice(ACTIONS)
        return f"演员面部特写，{action}，眼神带着狡黠和自信，额头有细微汗珠，嘴唇靠近麦克风。"
    else:
        # 默认随机
        return generate_main_prompt(random.choice(["comedian", "audience", "wide_stage", "closeup"]))

# 生成单个场景
def generate_scene(scene_id: int, video_id: int) -> Dict[str, Any]:
    # 场景类型：前两个场景通常是演员，后面可穿插观众、全景等
    # 为了让每个视频有起伏，根据 scene_id 决定类型
    if scene_id == 1:
        scene_type = "wide_stage"
    elif scene_id == 2:
        scene_type = "comedian"
    elif scene_id % 3 == 0:
        scene_type = "audience"
    elif scene_id % 5 == 0:
        scene_type = "backstage"
    else:
        scene_type = random.choice(["comedian", "closeup", "comedian"])
    
    main_prompt = generate_main_prompt(scene_type)
    # 添加一点随机主题变化，避免重复
    if scene_type == "comedian" and random.random() > 0.7:
        main_prompt = generate_main_prompt("comedian", topic=random.choice(TOPICS))
    
    return {
        "scene_id": scene_id,
        "duration_seconds": random.randint(*DURATION_RANGE),
        "main_prompt": main_prompt,
        "camera_movement": random.choice(CAMERA_MOVEMENTS),
        "character_id": random.choice(CHARACTER_IDS) if scene_type != "audience" else "audience_crowd",
        "style": random.choice(STYLES)
    }

# 生成一个完整视频（包含多个场景）
def generate_video(video_id: int) -> Dict[str, Any]:
    num_scenes = random.randint(*SCENES_PER_VIDEO_RANGE)
    scenes = []
    for sid in range(1, num_scenes + 1):
        scenes.append(generate_scene(sid, video_id))
    return {
        "video_id": video_id,
        "scenes": scenes
    }

def main():
    total_videos = 1000
    videos = [generate_video(i) for i in range(1, total_videos + 1)]
    
    # 输出为 JSON 文件
    output_file = "talk_show_videos_1000.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    
    print(f"已生成 {total_videos} 个脱口秀视频描述，保存至 {output_file}")

if __name__ == "__main__":
    main()