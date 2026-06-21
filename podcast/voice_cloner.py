"""
Voice Generation Module - 使用 CosyVoice 2 生成播客语音

为每个主播配置不同的播报风格：
- Matt Wolfe: lively（热情科技博主）
- Lenny's Podcast: relaxed（深夜电台闲聊）
- Dwarkesh Patel / Andrej Karpathy: serious（冷静权威）
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# ── 播报风格配置 ──────────────────────────────────────────

TTS_STYLES = {
    "serious": {
        "label": "科技大佬动态",
        "desc": "沉稳、权威、冷静",
    },
    "lively": {
        "label": "科技工具/AI 评测",
        "desc": "热情、活泼、有感染力",
    },
    "relaxed": {
        "label": "行业八卦/闲聊",
        "desc": "慵懒、亲切、思考感",
    },
}

# 各频道默认风格
CHANNEL_STYLES = {
    "Matt Wolfe": "lively",
    "Lenny's Podcast": "relaxed",
    "Dwarkesh Patel": "serious",
    "Andrej Karpathy": "serious",
}


class VoiceGenerator:
    """使用 CosyVoice 2 生成播客语音。"""

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from podcast.cosyvoice_tts import CosyVoiceEngine
            self._engine = CosyVoiceEngine()
        return self._engine

    def generate_tts(
        self,
        text: str,
        output_path: str,
        person_name: str = "",
        voice_override: str = "",
        style_override: str = "",
    ) -> dict:
        """
        生成 TTS 音频（仅 CosyVoice，无 edge-tts 回退）。

        Args:
            text: 播客脚本
            output_path: 输出 MP3 路径
            person_name: 频道名称（用于选择风格）
            voice_override: 保留参数（不再使用）
            style_override: 强制指定风格 (serious/lively/relaxed)

        Returns:
            {filepath, duration_seconds, size_bytes, style, style_label}
        """
        style = style_override or CHANNEL_STYLES.get(person_name, "lively")
        if style not in TTS_STYLES:
            style = "lively"

        style_label = TTS_STYLES[style]["label"]

        logger.info(
            "CosyVoice TTS: person=%s style=%s(%s)",
            person_name, style, style_label,
        )

        engine = self._get_engine()
        result = engine.generate(text, output_path, style=style)
        result["style"] = style
        result["style_label"] = style_label
        result["voice"] = "cosyvoice"
        return result


# 模块级单例
_generator = VoiceGenerator()


def get_voice_cloner() -> VoiceGenerator:
    """获取 VoiceGenerator 单例。（兼容旧名称）"""
    return _generator
