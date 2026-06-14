"""
翻译模块 —— 使用 DeepSeek 的 Anthropic 兼容 API 进行 AI 科技内容翻译与播客脚本制作。

功能：
- 将英文 AI 科技内容翻译成自然流畅的中文
- 添加播客风格的开场和结尾
- 支持长文本拆分、重试机制和日志记录
"""

import os
import time
import logging
from typing import Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)


def get_client() -> Anthropic:
    """获取 DeepSeek 的 Anthropic 兼容 API 客户端。

    优先从环境变量 ANTHROPIC_API_KEY 读取 API key，
    若未设置则尝试从项目根目录的 .env 文件中加载。

    Returns:
        Anthropic: 配置好的 Anthropic 客户端实例。

    Raises:
        ValueError: 未找到 API key 时抛出。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment or .env file")
    return Anthropic(api_key=api_key, base_url="https://api.deepseek.com/anthropic")


# ---------------------------------------------------------------------------
# 核心翻译
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是一个专业的 AI 科技内容翻译专家。请将以下英文内容翻译成自然流畅的中文。\n"
    "要求：\n"
    "1. 保持 AI 技术术语的准确性（如 AGI、LLM、Transformer 等专业词汇保留英文或使用公认译法）\n"
    "2. 语气保持原文风格——Matt Wolfe 的风格是热情、易懂、有见解\n"
    "3. 中文表达要口语化、适合收听，避免书面翻译腔\n"
    "4. 长句拆解为短句，加入自然的停顿和连接词\n"
    "5. 保留重要的人名、产品名、公司名（括号标注英文原名）"
)


def _split_text(text: str, max_chars: int = 10000) -> list[str]:
    """将长文本按段落边界拆分为多个块，每块不超过 max_chars 字符。

    Args:
        text: 待拆分的原始文本。
        max_chars: 每块的最大字符数，默认 10000。

    Returns:
        拆分后的文本块列表。
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    current_chunk: list[str] = []

    for para in paragraphs:
        if sum(len(p) for p in current_chunk) + len(para) + 2 > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
        current_chunk.append(para)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def translate_text(
    text: str,
    model: str = "deepseek-v4-flash",
    max_tokens: int = 4096,
    max_retries: int = 3,
    **kwargs,
) -> str:
    """将英文文本翻译成中文。

    支持最长 10000 字符的文本。对于更长的文本，自动按段落边界拆分后逐块翻译。

    Args:
        text: 待翻译的英文文本。
        model: DeepSeek 模型名称，默认为 "deepseek-v4-flash"。
        max_tokens: 每次 API 调用的最大 token 数，默认为 4096。
        max_retries: API 调用失败时的最大重试次数，默认为 3。

    Returns:
        翻译后的中文文本。

    Raises:
        RuntimeError: 所有重试均失败时抛出。
    """
    client = get_client()
    chunks = _split_text(text)
    translated_chunks: list[str] = []

    for idx, chunk in enumerate(chunks):
        logger.info("翻译进度: 第 %d/%d 块 (长度 %d 字符)", idx + 1, len(chunks), len(chunk))
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": chunk}],
                    **kwargs,
                )
                translated = response.content[0].text
                translated_chunks.append(translated)
                logger.info("第 %d 块翻译完成 (尝试 %d 次)", idx + 1, attempt)
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "第 %d 块翻译失败 (尝试 %d/%d): %s",
                    idx + 1,
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    sleep_time = 2 ** attempt
                    logger.info("等待 %d 秒后重试...", sleep_time)
                    time.sleep(sleep_time)

        if last_error is not None:
            error_msg = f"翻译失败: 第 {idx + 1} 块在 {max_retries} 次重试后仍未成功"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from last_error

    return "\n\n".join(translated_chunks)


# ---------------------------------------------------------------------------
# 播客润色
# ---------------------------------------------------------------------------

POLISH_SYSTEM_PROMPT = (
    "你是一个 AI 科技播客脚本编辑。请将以下翻译好的中文内容润色为适合播客收听的脚本。\n"
    "要求：\n"
    "1. 添加自然的开场白和结束语\n"
    "2. 使用口语化的表达，听起来像在和朋友聊天\n"
    "3. 加入适当的空行分段，便于 TTS 朗读时自然停顿\n"
    "4. 保持 Matt Wolfe 热情、易懂、有见解的风格\n"
    "5. 不要改变原意，只需调整表达方式"
)


def polish_for_podcast(
    translated_text: str,
    video_title: str,
    video_url: str = "",
    model: str = "deepseek-v4-flash",
    max_tokens: int = 4096,
    max_retries: int = 3,
    **kwargs,
) -> str:
    """为翻译后的文本添加播客风格的开场和结尾。

    Args:
        translated_text: 已翻译的中文文本。
        video_title: 视频标题，用于开场白。
        video_url: 视频链接（可选），用于开场白。
        model: DeepSeek 模型名称，默认为 "deepseek-v4-flash"。
        max_tokens: 每次 API 调用的最大 token 数，默认为 4096。
        max_retries: API 调用失败时的最大重试次数，默认为 3。

    Returns:
        润色后的播客脚本，可直接用于 TTS。
    """
    client = get_client()

    url_part = f"（视频链接：{video_url}）" if video_url else ""
    user_prompt = (
        f"视频标题：{video_title}\n{url_part}\n\n"
        f"待润色的中文内容：\n{translated_text}\n\n"
        f"请为以上内容添加播客风格的开场和结尾。\n"
        f"开场示例：「大家好，欢迎收听 Matt Wolfe 中文播报。今天我们来聊一聊：{video_title}」\n"
        f"结尾示例：「以上就是本期 Matt Wolfe 中文播报的全部内容。如果觉得有帮助，欢迎分享给更多朋友。我们下期再见！」\n"
        f"注意加入自然的空行分段，保持口语化和适合 TTS 的风格。"
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=POLISH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                **kwargs,
            )
            logger.info("播客润色完成 (尝试 %d 次)", attempt)
            return response.content[0].text
        except Exception as exc:
            last_error = exc
            logger.warning("播客润色失败 (尝试 %d/%d): %s", attempt, max_retries, exc)
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info("等待 %d 秒后重试...", sleep_time)
                time.sleep(sleep_time)

    error_msg = f"播客润色失败: {max_retries} 次重试后仍未成功"
    logger.error(error_msg)
    raise RuntimeError(error_msg) from last_error


# ---------------------------------------------------------------------------
# 合并流程
# ---------------------------------------------------------------------------

COMBINED_SYSTEM_PROMPT = (
    "你是一个专业的 AI 科技内容翻译专家和播客脚本编辑。\n"
    "请将以下英文内容翻译成自然流畅的中文，并润色为适合播客收听的脚本格式。\n\n"
    "翻译要求：\n"
    "1. 保持 AI 技术术语的准确性（如 AGI、LLM、Transformer 等专业词汇保留英文或使用公认译法）\n"
    "2. 语气保持原文风格——Matt Wolfe 的风格是热情、易懂、有见解\n"
    "3. 中文表达要口语化、适合收听，避免书面翻译腔\n"
    "4. 长句拆解为短句，加入自然的停顿和连接词\n"
    "5. 保留重要的人名、产品名、公司名（括号标注英文原名）\n\n"
    "播客格式要求：\n"
    "1. 开头添加：「大家好，欢迎收听 Matt Wolfe 中文播报。今天我们来聊一聊：<标题>」\n"
    "2. 结尾添加：「以上就是本期 Matt Wolfe 中文播报的全部内容。如果觉得有帮助，欢迎分享给更多朋友。我们下期再见！」\n"
    "3. 正文加入空行分段，保持口语化和适合 TTS 的风格"
)


def translate_and_polish(
    text: str,
    video_title: str,
    video_url: str = "",
    model: str = "deepseek-v4-flash",
    max_tokens: int = 4096,
    max_retries: int = 3,
    **kwargs,
) -> str:
    """一步完成翻译和播客润色。

    将英文文本直接翻译并润色为播客脚本，比分开调用更高效（一次 API 调用完成两项工作）。

    Args:
        text: 待翻译的英文文本。
        video_title: 视频标题。
        video_url: 视频链接（可选）。
        model: DeepSeek 模型名称，默认为 "deepseek-v4-flash"。
        max_tokens: 每次 API 调用的最大 token 数，默认为 4096。
        max_retries: API 调用失败时的最大重试次数，默认为 3。
        **kwargs: 传递给 Anthropic API 的额外参数。

    Returns:
        翻译并润色后的播客脚本，可直接用于 TTS。
    """
    client = get_client()
    chunks = _split_text(text)

    if len(chunks) == 1:
        return _translate_and_polish_single(
            text, video_title, video_url, client, model, max_tokens, max_retries, **kwargs
        )

    # 多块：逐块翻译，最后统一润色（forward kwargs）
    translated = translate_text(text, model, max_tokens, max_retries, **kwargs)
    return polish_for_podcast(translated, video_title, video_url, model, max_tokens, max_retries, **kwargs)


def _translate_and_polish_single(
    text: str,
    video_title: str,
    video_url: str,
    client: Anthropic,
    model: str,
    max_tokens: int,
    max_retries: int,
    **kwargs,
) -> str:
    """单块文本的一次性翻译+润色（内部辅助函数）。"""
    url_part = f"（视频链接：{video_url}）" if video_url else ""
    user_prompt = (
        f"视频标题：{video_title}\n{url_part}\n\n"
        f"待处理的英文内容：\n{text}"
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=COMBINED_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                **kwargs,
            )
            logger.info("翻译+润色一步完成 (尝试 %d 次)", attempt)
            return response.content[0].text
        except Exception as exc:
            last_error = exc
            logger.warning(
                "翻译+润色失败 (尝试 %d/%d): %s", attempt, max_retries, exc
            )
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info("等待 %d 秒后重试...", sleep_time)
                time.sleep(sleep_time)

    error_msg = f"翻译+润色失败: {max_retries} 次重试后仍未成功"
    logger.error(error_msg)
    raise RuntimeError(error_msg) from last_error


# ---------------------------------------------------------------------------
# 完整播客脚本生成
# ---------------------------------------------------------------------------

PIPELINE_SYSTEM_PROMPT = (
    "你是一个 AI 科技内容播客脚本制作专家。\n"
    "请根据提供的视频元数据（标题、描述）和英文字幕转录文本，制作一份完整的、可直接用于 TTS 录制的中文播客脚本。\n\n"
    "要求：\n"
    "1. 开场白：「大家好，欢迎收听 Matt Wolfe 中文播报。今天我们来聊一聊：<视频标题>」\n"
    "2. 正文：将英文转录准确翻译成中文，保持热情易懂的风格，长句拆短句，口语化表达\n"
    "3. 术语准确：AGI、LLM、Transformer 等保留英文或使用公认译法\n"
    "4. 人名/产品名/公司名保留并括号标注英文原名\n"
    "5. 正文中加入自然空行分段，便于 TTS 停顿\n"
    "6. 结尾：「以上就是本期 Matt Wolfe 中文播报的全部内容。如果觉得有帮助，欢迎分享给更多朋友。我们下期再见！」\n"
    "7. 如果视频描述中有重要背景信息，可以自然地融入正文介绍中"
)


def get_podcast_script(
    video_title: str,
    video_description: str,
    transcript: str,
    model: str = "deepseek-v4-flash",
    max_tokens: int = 8192,
    max_retries: int = 3,
) -> str:
    """从视频元数据和英文转录生成完整的播客脚本。

    这是完整流水线：一次性将英文转录翻译、润色、添加开场结尾，
    生成可直接交付 TTS 的中文播客脚本。

    Args:
        video_title: 视频标题。
        video_description: 视频描述/简介。
        transcript: 英文字幕转录文本。
        model: DeepSeek 模型名称，默认为 "deepseek-v4-flash"。
        max_tokens: 每次 API 调用的最大 token 数，默认为 8192。
        max_retries: API 调用失败时的最大重试次数，默认为 3。

    Returns:
        完整的中文播客脚本，可直接用于 TTS 录制。

    Raises:
        RuntimeError: 所有重试均失败时抛出。
    """
    client = get_client()

    user_prompt = (
        f"视频标题：{video_title}\n\n"
        f"视频描述：\n{video_description}\n\n"
        f"英文转录：\n{transcript}\n\n"
        f"请根据以上信息制作一份完整的中文播客脚本。"
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=PIPELINE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            logger.info("播客脚本生成完成 (尝试 %d 次)", attempt)
            return response.content[0].text
        except Exception as exc:
            last_error = exc
            logger.warning(
                "播客脚本生成失败 (尝试 %d/%d): %s", attempt, max_retries, exc
            )
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info("等待 %d 秒后重试...", sleep_time)
                time.sleep(sleep_time)

    error_msg = f"播客脚本生成失败: {max_retries} 次重试后仍未成功"
    logger.error(error_msg)
    raise RuntimeError(error_msg) from last_error


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    test_text = (
        "Today we're talking about the latest developments in AI. "
        "Google just released a new model that can understand video content."
    )
    result = translate_and_polish(test_text, "Test Video")
    print(result)
