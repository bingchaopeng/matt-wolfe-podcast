"""
CosyVoice 2 TTS Module - 使用 CosyVoice 2 inference_instruct2 生成播客语音

替换 edge-tts 成为主要 TTS 引擎。利用 GPU (RTX 3050) 进行 fp16 推理，
生成 pcm_f32le 24000Hz 单声道 WAV，最终转为 MP3。

性能：RTF ~15-21x，600s 播客约需 2.5-3.5 小时。
"""

import os
import re
import sys
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import torch
import torchaudio

logger = logging.getLogger(__name__)

# ── CosyVoice 2 环境配置 ──────────────────────────────────
COSYVOICE_SRC = Path(__file__).parent.parent / "cosyvoice-src"
sys.path.insert(0, str(COSYVOICE_SRC))
sys.path.insert(0, str(COSYVOICE_SRC / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import AutoModel

# 默认参考音频（语音克隆参考）
DEFAULT_PROMPT_WAV = str(COSYVOICE_SRC / "asset" / "zero_shot_prompt.wav")

# ── 播报风格 → instruct 提示词 ───────────────────────────
# inference_instruct2 的 instruct_text 格式：风格描述 <|endofprompt|>
STYLE_INSTRUCTS = {
    "lively": (
        "You are a lively and passionate tech podcaster. "
        "热情、充满活力，语速稍快，带有感染力和轻微的惊讶感。"
        "像在跟朋友分享好东西，允许适当的语气词。<|endofprompt|>"
    ),
    "serious": (
        "You are a serious and authoritative tech journalist. "
        "冷静、客观、沉稳，语速中等偏慢，字正腔圆。"
        "强调逻辑重音，不要夸张，保持专业感。<|endofprompt|>"
    ),
    "relaxed": (
        "You are a relaxing late-night radio host. "
        "慵懒、随性、亲切，语速舒缓，带有思考感。"
        "偶尔带一点笑意，自然的停顿。<|endofprompt|>"
    ),
}


class CosyVoiceEngine:
    """CosyVoice 2 TTS 引擎单例。

    模型只加载一次（~2min），常驻 GPU 显存，
    后续调用直接推理。
    """

    _instance = None
    _model = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── 模型加载 ──

    def load(self, model_dir: Optional[str] = None) -> None:
        """加载 CosyVoice 2 模型（仅首次调用生效）。"""
        if self._loaded and self._model is not None:
            return
        if model_dir is None:
            model_dir = str(COSYVOICE_SRC / "pretrained_models" / "CosyVoice2-0.5B")
        logger.info("Loading CosyVoice 2 from %s ...", model_dir)
        self._model = AutoModel(model_dir=model_dir, fp16=True)
        self._loaded = True
        logger.info(
            "CosyVoice 2 loaded. Sample rate: %d",
            self._model.sample_rate,
        )

    @property
    def model(self):
        if not self._loaded:
            self.load()
        return self._model

    @property
    def sample_rate(self) -> int:
        return self.model.sample_rate

    # ── 核心生成 ──

    def _generate_chunk(
        self,
        text: str,
        style: str = "lively",
        prompt_wav: Optional[str] = None,
    ) -> torch.Tensor:
        """生成单个文本块的音频。

        Returns:
            Tensor shape (1, num_samples), dtype float32, 24000Hz.
        """
        if prompt_wav is None:
            prompt_wav = DEFAULT_PROMPT_WAV

        instruct = STYLE_INSTRUCTS.get(style, STYLE_INSTRUCTS["lively"])

        result = self.model.inference_instruct2(
            text, instruct, prompt_wav, stream=False
        )

        tensors = [j["tts_speech"] for j in result]
        if not tensors:
            raise RuntimeError("CosyVoice generated no audio for chunk")

        out = torch.cat(tensors, dim=-1)
        # Free intermediate tensors
        del tensors
        torch.cuda.empty_cache()
        return out

    def generate(
        self,
        text: str,
        output_path: str,
        style: str = "lively",
        prompt_wav: Optional[str] = None,
        max_chunk_chars: int = 300,
        mp3_bitrate: str = "192k",
    ) -> dict:
        """生成完整 TTS 音频并保存为 MP3。

        Args:
            text: 播客脚本文本
            output_path: 输出 MP3 路径
            style: 播报风格 (lively/serious/relaxed)
            prompt_wav: 参考音频路径（语音克隆用）
            max_chunk_chars: 每块最大字符数（CosyVoice 分块用）
            mp3_bitrate: MP3 码率

        Returns:
            {filepath, duration_seconds, size_bytes, style}
        """
        # 1. 生成 WAV（分块处理长文本）
        if len(text) <= max_chunk_chars:
            logger.info("Generating single chunk (%d chars)", len(text))
            audio = self._generate_chunk(text, style, prompt_wav)
            wav_path = output_path + ".tmp.wav"
            torchaudio.save(wav_path, audio.cpu(), self.sample_rate)
        else:
            chunks = self._split_text(text, max_chunk_chars)
            logger.info("Generating %d chunks (max %d chars each)", len(chunks), max_chunk_chars)

            chunk_files = []
            for i, chunk in enumerate(chunks):
                logger.info("  Chunk %d/%d: %d chars", i + 1, len(chunks), len(chunk))
                # Clear GPU cache before each chunk to avoid OOM on 4GB card
                torch.cuda.empty_cache()
                chunk_audio = self._generate_chunk(chunk, style, prompt_wav)
                chunk_path = output_path + f".chunk_{i:04d}.wav"
                torchaudio.save(chunk_path, chunk_audio.cpu(), self.sample_rate)
                chunk_files.append(chunk_path)
                # Free GPU memory
                del chunk_audio
                torch.cuda.empty_cache()

            wav_path = self._concat_wavs(chunk_files, output_path + ".tmp.wav")
            self._cleanup(chunk_files)

        # 2. WAV → MP3
        mp3_path = output_path
        self._wav_to_mp3(wav_path, mp3_path, mp3_bitrate)
        if os.path.exists(wav_path):
            os.remove(wav_path)

        # 3. 获取元数据
        duration = self._get_duration(mp3_path)
        size = os.path.getsize(mp3_path)

        logger.info(
            "CosyVoice audio generated: %s (%.1fs, %dMB, %s)",
            mp3_path, duration, size // (1024 * 1024), style,
        )

        return {
            "filepath": mp3_path,
            "duration_seconds": duration,
            "size_bytes": size,
            "style": style,
        }

    # ── 文本切分 ──

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        """按句子边界切分文本，每块不超过 max_chars。"""
        sentences = re.split(r"(?<=[。！？\n])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= max_chars:
                current += s
            else:
                if current:
                    chunks.append(current)
                if len(s) > max_chars:
                    for i in range(0, len(s), max_chars):
                        chunks.append(s[i : i + max_chars])
                    current = ""
                else:
                    current = s
        if current:
            chunks.append(current)
        return chunks

    # ── 音频处理 ──

    @staticmethod
    def _concat_wavs(wav_files: list[str], output_path: str) -> str:
        """用 ffmpeg concat 拼接多个同格式 WAV。"""
        list_path = output_path + ".list.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for wf in wav_files:
                f.write(f"file '{wf}'\n")
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0",
             "-i", list_path, "-c", "copy", "-y", output_path],
            check=True, capture_output=True, timeout=3600,
        )
        os.remove(list_path)
        return output_path

    @staticmethod
    def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k"):
        """WAV → MP3 转换。"""
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path,
             "-codec:a", "libmp3lame", "-b:a", bitrate,
             mp3_path],
            check=True, capture_output=True, timeout=600,
        )

    @staticmethod
    def _cleanup(files: list[str]):
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass

    @staticmethod
    def _get_duration(audio_path: str) -> float:
        """获取音频时长（秒）。"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 audio_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (ValueError, subprocess.SubprocessError):
            pass
        return 0.0


# ── 模块级单例 ──
_engine = CosyVoiceEngine()


def get_engine() -> CosyVoiceEngine:
    """获取 CosyVoice 引擎单例。"""
    return _engine


def generate_audio(
    text: str,
    output_path: str,
    style: str = "lively",
    prompt_wav: Optional[str] = None,
    **kwargs,
) -> dict:
    """快捷函数：使用 CosyVoice 生成音频。"""
    engine = get_engine()
    return engine.generate(text, output_path, style=style, prompt_wav=prompt_wav, **kwargs)
