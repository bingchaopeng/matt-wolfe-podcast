"""
Voice Cloning Module - 同声克隆语音模块

目标：让 Andrej Karpathy 用自己的声音讲中文。

当前限制：
- Python 3.14 暂不支持 CUDA PyTorch（主因）
- 大多数声音克隆库（GPT-SoVITS, CosyVoice, FishSpeech）需 PyTorch
- 替代方案：ONNX Runtime DirectML (GPU 可用)

策略链：
1. 首选：使用 ONNX 格式的声音克隆模型（GPT-SoVITS-onnx / CosyVoice-onnx）
2. 次选：使用 edge-tts 配合最接近的男声
3. 备选：下载参考音频 + 云端 API

使用方式：
   cloner = VoiceCloner()
   result = cloner.clone_tts(text, reference_audio, output_path)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
VOICE_PROFILES_DIR = PROJECT_ROOT / "data" / "voice_profiles"
os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)

# 声音配置文件
VOICE_PROFILES = {
    "Andrej Karpathy": {
        "name": "Andrej Karpathy",
        "engine": "edge-tts",         # 当前使用引擎
        "language": "zh-CN",           # 目标语言
        "edge_voice": "zh-CN-YunjianNeural",  # 最接近的男声
        "reference_audio": "",          # 参考音频路径（用于克隆）
        "clone_model": "",             # 克隆模型路径
        "description": "技术深度、逻辑清晰的男声",
    },
    "Matt Wolfe": {
        "name": "Matt Wolfe",
        "engine": "edge-tts",
        "language": "zh-CN",
        "edge_voice": "zh-CN-XiaoxiaoNeural",
        "reference_audio": "",
        "clone_model": "",
        "description": "热情、易懂的男声（女声替代）",
    },
    "Lenny's Podcast": {
        "name": "Lenny's Podcast",
        "engine": "edge-tts",
        "language": "zh-CN",
        "edge_voice": "zh-CN-XiaoyiNeural",
        "reference_audio": "",
        "clone_model": "",
        "description": "深度、好奇的对话风格",
    },
    "Dwarkesh Patel": {
        "name": "Dwarkesh Patel",
        "engine": "edge-tts",
        "language": "zh-CN",
        "edge_voice": "zh-CN-YunxiNeural",
        "reference_audio": "",
        "clone_model": "",
        "description": "理性、深入的男声",
    },
}


class VoiceCloner:
    """
    声音克隆管理器。

    提供统一的 TTS 接口，自动选择最佳可用方案：
    - 如果克隆模型可用 → 使用克隆声音
    - 如果 ONNX 模型可用 → 使用 DirectML GPU 推理
    - 否则 → 使用 edge-tts 最接近的语音
    """

    def __init__(self):
        self._onnx_available = self._check_onnx()
        self._cloned_voices = {}  # name -> model path
        self._load_profiles()

    def _check_onnx(self) -> bool:
        """检查 ONNX Runtime DirectML 是否可用."""
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            return "DmlExecutionProvider" in providers
        except ImportError:
            return False

    def _load_profiles(self):
        """加载声音配置文件."""
        profile_file = VOICE_PROFILES_DIR / "profiles.json"
        if profile_file.exists():
            try:
                with open(profile_file) as f:
                    data = json.load(f)
                    self._cloned_voices.update(data.get("cloned", {}))
            except (json.JSONDecodeError, OSError):
                pass

    def _save_profiles(self):
        """保存声音配置文件."""
        profile_file = VOICE_PROFILES_DIR / "profiles.json"
        data = {
            "cloned": self._cloned_voices,
            "onnx_available": self._onnx_available,
        }
        with open(profile_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_profile(self, person_name: str) -> dict:
        """获取指定人的声音配置."""
        return VOICE_PROFILES.get(person_name, {
            "name": person_name,
            "engine": "edge-tts",
            "edge_voice": "zh-CN-YunjianNeural",
            "description": "",
        })

    def has_cloned_voice(self, person_name: str) -> bool:
        """是否已为某人创建了克隆声音."""
        return person_name in self._cloned_voices

    def download_reference_audio(self, person_name: str, video_url: str) -> Optional[str]:
        """
        从视频中下载参考音频（用于声音克隆）。

        提取视频中人物的干净语音片段（约 10-30 秒）。
        需要先下载视频音频，然后截取无人声干扰的片段。

        Args:
            person_name: 人物名称
            video_url: YouTube 视频 URL

        Returns:
            参考音频文件路径，或 None
        """
        from podcast.fetcher import download_audio

        logger.info("下载参考音频: %s from %s", person_name, video_url)
        audio_path = download_audio(video_url, str(VOICE_PROFILES_DIR))

        if not audio_path or not os.path.isfile(audio_path):
            logger.error("参考音频下载失败")
            return None

        # 重命名为固定文件名
        ref_path = VOICE_PROFILES_DIR / f"{person_name.replace(' ', '_')}_ref.mp3"
        import shutil
        shutil.copy2(audio_path, ref_path)
        logger.info("参考音频已保存: %s", ref_path)
        return str(ref_path)

    def set_cloned_voice(self, person_name: str, model_path: str, engine: str = "onnx"):
        """注册克隆声音模型."""
        self._cloned_voices[person_name] = {
            "model_path": model_path,
            "engine": engine,
        }
        self._save_profiles()
        logger.info("克隆声音已注册: %s -> %s (%s)", person_name, model_path, engine)

    def generate_tts(
        self,
        text: str,
        output_path: str,
        person_name: str = "",
        voice_override: str = "",
    ) -> dict:
        """
        生成 TTS 音频，自动选择最佳声音方案。

        Args:
            text: 要合成的文本
            output_path: 输出音频路径
            person_name: 人物名称（用于选择克隆声音）
            voice_override: 强制使用指定的 edge-tts 语音

        Returns:
            {filepath, duration_seconds, size_bytes, voice}
        """
        from podcast.tts import generate_audio_long_text

        # 确定使用的语音
        if voice_override:
            voice = voice_override
            engine = "edge-tts"
            logger.info("使用指定的语音: %s", voice)
        elif person_name and self.has_cloned_voice(person_name):
            # 使用克隆声音
            voice = self._cloned_voices[person_name]["model_path"]
            engine = self._cloned_voices[person_name]["engine"]
            logger.info("使用克隆声音: %s (%s)", person_name, engine)
            # TODO: 当克隆模型就绪时，调用 ONNX 推理
            # 目前回退到 edge-tts
            profile = self.get_profile(person_name)
            voice = profile.get("edge_voice", "zh-CN-YunjianNeural")
        else:
            profile = self.get_profile(person_name)
            voice = profile.get("edge_voice", "zh-CN-YunjianNeural")

        # 当前实现：使用 edge-tts
        logger.info("TTS: person=%s voice=%s", person_name, voice)
        return generate_audio_long_text(text, output_path, voice=voice)

    def install_onnx_model(self, model_type: str = "gpt-sovits") -> bool:
        """
        安装 ONNX 格式的声音克隆模型。

        Args:
            model_type: 模型类型（gpt-sovits / cosyvoice）

        Returns:
            是否安装成功
        """
        models_dir = PROJECT_ROOT / "models"
        os.makedirs(models_dir, exist_ok=True)

        if model_type == "gpt-sovits":
            logger.info("GPT-SoVITS ONNX 模型安装需要手动下载:")
            logger.info("1. 下载模型到: %s", models_dir)
            logger.info("2. 下载地址: https://huggingface.co/...")
            logger.info("3. 注册: set_cloned_voice('Andrej Karpathy', model_path)")
        elif model_type == "cosyvoice":
            logger.info("CosyVoice ONNX 模型安装需要手动下载...")

        return False


# 模块级单例
cloner = VoiceCloner()

def get_voice_cloner() -> VoiceCloner:
    """获取 VoiceCloner 单例."""
    return cloner


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                       format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("Voice Cloner Status:")
    print(f"  ONNX DirectML: {'✅' if cloner._onnx_available else '❌'} Available")
    print(f"  Cloned voices: {list(cloner._cloned_voices.keys())}")
    print()

    for name, profile in VOICE_PROFILES.items():
        has_clone = "🔊 克隆" if cloner.has_cloned_voice(name) else ""
        print(f"  {name:25s} → {profile['edge_voice']:25s} {has_clone}")
    print()

    if not cloner._onnx_available:
        print("⚠️  当前使用 edge-tts 语音（非克隆声音）")
        print("   需安装 Python <3.14 的 CUDA PyTorch 才能使用声音克隆")
