"""
TTS (Text-to-Speech) 模块 - 使用 edge-tts 将中文文本转换为语音
适用于 Matt Wolfe 中文播客项目
"""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

import edge_tts

logger = logging.getLogger(__name__)


def get_audio_duration(filepath: str) -> float:
    """
    获取音频文件的时长（秒）。

    优先使用 ffprobe（来自 ffmpeg）获取精确时长。
    如果 ffprobe 不可用，则根据中文文本粗略估计（约每秒 30 个字符）。

    Args:
        filepath: 音频文件路径

    Returns:
        音频时长（秒）
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            if duration > 0:
                return duration
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, OSError) as exc:
        logger.warning("ffprobe 不可用或执行失败，将使用估计值: %s", exc)

    # 估算：中文文本平均每秒约 30 个字符
    # 从文件名中提取字符数（无法获取实际文本时返回默认值）
    logger.info("使用估计时长（ffprobe 不可用）")
    return 0.0


def _estimate_duration_from_text(text: str) -> float:
    """
    根据文本长度估计音频时长。

    中文播报速度约为每秒 3-4 个汉字，取中间值 3.5。

    Args:
        text: 文本内容

    Returns:
        估计时长（秒）
    """
    char_count = len(text.strip())
    return char_count / 3.5


def generate_audio(
    text: str,
    output_path: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    将中文文本转换为语音并保存为音频文件。

    Args:
        text: 要转换为语音的文本
        output_path: 输出音频文件路径（推荐 .mp3 格式）
        voice: edge-tts 语音名称，默认为 "zh-CN-XiaoxiaoNeural"
        rate: 语速调整，例如 "+10%" 加快 10%，"-10%" 减慢 10%
        volume: 音量调整，例如 "+10%" 增加 10%，"-10%" 减少 10%

    Returns:
        包含生成结果的字典：
        - filepath: 输出文件路径
        - duration_seconds: 音频时长（秒）
        - size_bytes: 文件大小（字节）
        - voice: 使用的语音名称

    Raises:
        RuntimeError: 音频生成失败时抛出
    """
    async def _run() -> None:
        """异步执行 edge-tts 语音合成。"""
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        await communicate.save(output_path)

    try:
        logger.info("开始生成音频: voice=%s, rate=%s, volume=%s", voice, rate, volume)
        logger.info("文本长度: %d 字符", len(text))
        asyncio.run(_run())
    except Exception as exc:
        logger.error("edge-tts 生成失败: %s", exc)
        raise RuntimeError(f"音频生成失败: {exc}") from exc

    # 验证输出文件
    if not os.path.exists(output_path):
        raise RuntimeError(f"输出文件未生成: {output_path}")

    # 获取时长和大小
    duration = get_audio_duration(output_path)
    if duration <= 0:
        duration = _estimate_duration_from_text(text)
        logger.info("使用估计时长: %.2f 秒", duration)

    size = os.path.getsize(output_path)
    logger.info("音频生成完成: %s (%.2f 秒, %d 字节)", output_path, duration, size)

    return {
        "filepath": output_path,
        "duration_seconds": duration,
        "size_bytes": size,
        "voice": voice,
    }


def list_available_voices(language: str = "zh") -> List[Dict[str, Any]]:
    """
    列出可用的 edge-tts 语音。

    Args:
        language: 语言筛选条件，默认为 "zh"（中文）。
                  传入空字符串可列出所有语音。

    Returns:
        语音列表，每个语音包含以下字段：
        - name: 语音完整名称
        - short_name: 语音短名称
        - gender: 性别（Male/Female）
        - locale: 区域设置
        - description: 语音描述

    Raises:
        RuntimeError: 获取语音列表失败时抛出
    """
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as exc:
        logger.error("获取语音列表失败: %s", exc)
        raise RuntimeError(f"无法获取语音列表: {exc}") from exc

    result = []
    for v in voices:
        if language and not v.get("Locale", "").startswith(language):
            continue
        result.append({
            "name": v.get("Name", ""),
            "short_name": v.get("ShortName", ""),
            "gender": v.get("Gender", ""),
            "locale": v.get("Locale", ""),
            "description": v.get("LocalName", ""),
        })

    return result


def generate_audio_long_text(
    text: str,
    output_path: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    max_chunk_chars: int = 2500,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    处理长文本的语音生成。

    edge-tts 对单次生成的文本长度有限制。本函数将长文本按中文句子边界
    （。！？）切分为多个块，分别生成音频后拼接。

    拼接方式优先级：
    1. pydub（如果已安装）
    2. 简单二进制拼接（MP3 帧格式支持直接拼接）

    Args:
        text: 要转换为语音的长文本
        output_path: 输出音频文件路径
        voice: edge-tts 语音名称
        max_chunk_chars: 每个块的最大字符数，默认 2500
        **kwargs: 传递给 generate_audio 的额外参数（rate、volume 等）

    Returns:
        与 generate_audio() 相同格式的字典

    Raises:
        RuntimeError: 任何块生成失败时抛出
    """
    # 如果文本较短，直接调用 generate_audio
    if len(text) <= max_chunk_chars:
        logger.info("文本长度在限制范围内，直接生成")
        return generate_audio(text, output_path, voice=voice, **kwargs)

    # 按中文句子边界切分文本
    sentences = _split_sentences(text)
    chunks: List[str] = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_chars:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # 如果单个句子超过最大长度，强制切分
            if len(sentence) > max_chunk_chars:
                # 按字符强制切分
                for i in range(0, len(sentence), max_chunk_chars):
                    chunks.append(sentence[i:i + max_chunk_chars])
                current_chunk = ""
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    logger.info("长文本已切分为 %d 个块", len(chunks))

    # 为每个块生成临时音频文件
    temp_dir = tempfile.mkdtemp(prefix="tts_chunk_")
    chunk_files: List[str] = []

    try:
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.mp3")
            logger.info("生成第 %d/%d 个块（%d 字符）", i + 1, len(chunks), len(chunk))
            try:
                generate_audio(chunk, chunk_path, voice=voice, **kwargs)
            except RuntimeError as exc:
                raise RuntimeError(f"第 {i + 1} 个块生成失败: {exc}") from exc
            chunk_files.append(chunk_path)

        # 拼接所有块
        _concatenate_audio_files(chunk_files, output_path)

        # 验证输出文件
        if not os.path.exists(output_path):
            raise RuntimeError(f"拼接后的文件未生成: {output_path}")

        # 获取总时长和大小
        duration = get_audio_duration(output_path)
        if duration <= 0:
            duration_sum = 0.0
            for chunk in chunks:
                duration_sum += _estimate_duration_from_text(chunk)
            duration = duration_sum
            logger.info("使用估计总时长: %.2f 秒", duration)

        size = os.path.getsize(output_path)
        logger.info("长文本音频生成完成: %s (%.2f 秒, %d 字节)", output_path, duration, size)

        return {
            "filepath": output_path,
            "duration_seconds": duration,
            "size_bytes": size,
            "voice": voice,
        }

    finally:
        # 清理临时文件
        _cleanup_temp_files(temp_dir)


def _split_sentences(text: str) -> List[str]:
    """
    将文本按中文句子边界切分。

    边界字符：。！？；\n
    保留标点符号在句子末尾。

    Args:
        text: 输入文本

    Returns:
        句子列表
    """
    # 使用正则表达式在句末标点后切分
    pattern = r"(?<=[。！？；\n])"
    parts = re.split(pattern, text)
    # 过滤空白项
    return [p for p in parts if p.strip()]


def _concatenate_audio_files(chunk_files: List[str], output_path: str) -> None:
    """
    将多个音频文件拼接为一个。

    拼接方式优先级：
    1. pydub（最准确，保留元数据）
    2. ffmpeg concat（无需额外库）
    3. 二进制拼接（最终回退，跳过除第一块外的 ID3 头）

    Args:
        chunk_files: 音频文件路径列表
        output_path: 输出文件路径

    Raises:
        RuntimeError: 拼接失败时抛出
    """
    if not chunk_files:
        raise RuntimeError("没有可拼接的音频文件")

    # 方法 1: pydub（最推荐）
    try:
        from pydub import AudioSegment  # type: ignore[import-untyped]

        combined = AudioSegment.empty()
        for f in chunk_files:
            segment = AudioSegment.from_mp3(f)
            combined += segment
        combined.export(output_path, format="mp3")
        logger.info("使用 pydub 完成音频拼接")
        return
    except ImportError:
        logger.info("pydub 未安装")
    except Exception as exc:
        logger.warning("pydub 拼接失败: %s", exc)

    # 方法 2: ffmpeg concat
    try:
        # 创建 ffmpeg concat 文件列表
        list_path = output_path + ".list.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for cf in chunk_files:
                f.write("file '{}'\n".format(cf.replace("'", "'\\''")))
        result = subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0",
             "-i", list_path,
             "-c", "copy",
             "-y", output_path],
            capture_output=True, text=True, timeout=120,
        )
        os.remove(list_path)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info("使用 ffmpeg concat 完成音频拼接")
            return
        logger.warning("ffmpeg concat 失败 (code %d): %s",
                       result.returncode, result.stderr.strip())
    except FileNotFoundError:
        logger.info("ffmpeg 未安装")
    except Exception as exc:
        logger.warning("ffmpeg concat 异常: %s", exc)

    # 方法 3: 二进制拼接（最终回退，跳过 ID3 头）
    try:
        with open(output_path, "wb") as outfile:
            for i, f in enumerate(chunk_files):
                with open(f, "rb") as infile:
                    data = infile.read()
                if i > 0:
                    # 跳过 ID3v2 头（前 10 字节标识，之后是头大小）
                    if data[:3] == b"ID3":
                        header_size = 10
                        if len(data) >= 10:
                            size_bytes = data[6:10]
                            id3_size = (
                                (size_bytes[0] << 21) |
                                (size_bytes[1] << 14) |
                                (size_bytes[2] << 7) |
                                size_bytes[3]
                            )
                            data = data[header_size + id3_size:]
                outfile.write(data)
        logger.info("使用二进制拼接（跳过 ID3）完成音频拼接")
    except OSError as exc:
        raise RuntimeError(f"音频文件拼接失败: {exc}") from exc


def _cleanup_temp_files(temp_dir: str) -> None:
    """
    清理临时文件和目录。

    Args:
        temp_dir: 临时目录路径
    """
    try:
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(temp_dir)
        logger.debug("临时文件已清理: %s", temp_dir)
    except OSError as exc:
        logger.warning("清理临时文件失败: %s", exc)


def get_recommended_voice() -> str:
    """
    获取推荐的默认语音名称。

    推荐 "zh-CN-XiaoxiaoNeural"（晓晓），这是最自然的中文女声，
    适合播客场景。同时会记录其他可用的中文语音供参考。

    Returns:
        推荐语音名称 "zh-CN-XiaoxiaoNeural"
    """
    recommended = "zh-CN-XiaoxiaoNeural"
    try:
        voices = list_available_voices("zh")
        logger.info("可用的中文语音:")
        for v in voices:
            logger.info("  - %s (%s, %s)", v["name"], v["gender"], v["description"])
    except RuntimeError as exc:
        logger.warning("无法获取可用语音列表: %s", exc)

    return recommended


def get_voice_info(voice: str) -> Dict[str, Any]:
    """
    获取指定语音的详细信息。

    Args:
        voice: 语音名称（如 "zh-CN-XiaoxiaoNeural"）

    Returns:
        语音信息字典，包含以下字段：
        - name: 语音完整名称
        - gender: 性别
        - locale: 区域设置
        - description: 语音描述

    Raises:
        ValueError: 未找到指定语音时抛出
    """
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as exc:
        logger.error("获取语音列表失败: %s", exc)
        raise RuntimeError(f"无法获取语音列表: {exc}") from exc

    for v in voices:
        if v.get("Name") == voice or v.get("ShortName") == voice:
            return {
                "name": v.get("Name", ""),
                "gender": v.get("Gender", ""),
                "locale": v.get("Locale", ""),
                "description": v.get("LocalName", ""),
            }

    raise ValueError(f"未找到语音: {voice}")


if __name__ == "__main__":
    # 使用简短中文文本进行测试
    test_text = "大家好，欢迎收听 Matt Wolfe 中文播报。今天我们来看看 AI 领域的最新动态。"
    result = generate_audio(test_text, "test_output.mp3")
    print(f"Generated: {result}")
