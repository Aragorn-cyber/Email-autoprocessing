import asyncio
import json
import logging
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

from app.core.config import ApplicationSettings
from app.core.exceptions import AnalysisValidationError, ExternalServiceError
from app.core.link_policy import report_links
from app.domain.entities import AnalyzedLink, FetchedEmail, SemanticAnalysis
from app.domain.interfaces import LanguageModelClient


logger = logging.getLogger(__name__)


class DeepSeekLanguageModel(LanguageModelClient):
    def __init__(self, settings: ApplicationSettings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.semaphore = asyncio.Semaphore(settings.llm_concurrency)

    async def analyze_email(
        self,
        email: FetchedEmail,
        category_names: tuple[str, ...],
    ) -> SemanticAnalysis:
        if not self.settings.llm_api_key:
            raise ExternalServiceError("未配置 LLM_API_KEY")
        system_prompt = (
            "你是邮件分类助手。必须只返回合法 JSON，不要 Markdown。"
            "JSON 字段必须包含 source_suggestion、category_name、category_suggestion、"
            "semantic_score、reason、summary、discard_reason_summary、link_summaries。"
            "source_suggestion 应是稳定的机构或平台名，不能使用邮箱地址、域名、收件箱、学校官方等泛称。"
            "category_name 必须严格选择可选二级分类之一；只有现有分类都不适用时，"
            "才将 category_name 设为其他，并在 category_suggestion 中提出一个真正的新类别。"
            "link_summaries 是数组，每项包含原样 url 和不超过 30 个汉字的用途摘要；"
            "忽略退订、追踪像素和无用户价值的链接。"
            f"可选二级分类：{', '.join(category_names)}。"
        )
        body_text = email.body_text
        if len(body_text) > self.settings.llm_body_char_limit:
            body_text = body_text[: self.settings.llm_body_char_limit] + "……（正文过长，已截断）"
        user_prompt = json.dumps(
            {
                "instruction": "请分析这封邮件。semantic_score 为 0 到 5 的整数。若判断为可丢弃，discard_reason_summary 必须是面向用户的简短原因摘要，否则可为 null。",
                "email": {
                    "subject": email.subject,
                    "sender_name": email.sender_name,
                    "sender_address": email.sender_address,
                    "sent_at": email.sent_at.isoformat() if email.sent_at else None,
                    "body": body_text,
                    "links": list(report_links(list(email.extracted_links))[:12]),
                },
                "json_example": {
                    "source_suggestion": None,
                    "category_name": "其他",
                    "category_suggestion": None,
                    "semantic_score": 2,
                    "reason": "判断依据",
                    "summary": "给用户看的摘要",
                    "discard_reason_summary": "群发推广且没有与你相关的行动要求",
                    "link_summaries": [
                        {"url": "https://example.com/register", "summary": "活动报名页面"}
                    ],
                },
            },
            ensure_ascii=False,
        )
        async with self.semaphore:
            for attempt in range(2):
                if attempt:
                    await asyncio.sleep(self.settings.llm_retry_backoff_seconds)
                try:
                    response = await self.client.chat.completions.create(
                        model=self.settings.llm_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        max_tokens=self.settings.llm_max_tokens,
                    )
                    content = response.choices[0].message.content or ""
                    if not content.strip():
                        self._log_empty_response(email, response)
                        if attempt == 0:
                            continue
                        return self._fallback_analysis(
                            email,
                            category_names,
                            AnalysisValidationError("DeepSeek 返回空内容"),
                        )
                    try:
                        analysis = self._parse(content)
                        analysis = self._complete_link_summaries(email, analysis)
                        self._require_link_summaries(email, analysis)
                        return analysis
                    except AnalysisValidationError as exc:
                        if attempt == 0:
                            continue
                        return self._fallback_analysis(email, category_names, exc)
                except (APIError, APITimeoutError, RateLimitError) as exc:
                    if attempt == 1:
                        raise ExternalServiceError(f"DeepSeek 调用失败：{exc}") from exc
        raise ExternalServiceError("DeepSeek 调用失败")

    @staticmethod
    def _log_empty_response(email: FetchedEmail, response: Any) -> None:
        try:
            choice = response.choices[0]
            logger.warning(
                "DeepSeek 返回空内容 subject=%r finish_reason=%r has_reasoning=%r",
                email.subject,
                getattr(choice, "finish_reason", None),
                bool(getattr(choice.message, "reasoning_content", None)),
            )
        except Exception:
            logger.warning("DeepSeek 返回空内容 subject=%r", email.subject)

    @staticmethod
    def _parse(content: str) -> SemanticAnalysis:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.removeprefix("```json").removeprefix("```")
            normalized = normalized.removesuffix("```").strip()
        try:
            payload: dict[str, Any] = json.loads(normalized)
            semantic_score = int(payload["semantic_score"])
            category_name = str(payload["category_name"]).strip()
            reason = str(payload["reason"]).strip()
            summary = str(payload["summary"]).strip()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AnalysisValidationError("DeepSeek 返回的 JSON 字段不完整或格式错误") from exc
        if not category_name or not reason or not summary:
            raise AnalysisValidationError("DeepSeek 返回的分类、理由或摘要为空")
        discard = payload.get("discard_reason_summary")
        link_summaries = DeepSeekLanguageModel._link_summaries(payload.get("link_summaries"))
        return SemanticAnalysis(
            source_suggestion=DeepSeekLanguageModel._optional_string(payload.get("source_suggestion")),
            category_name=category_name,
            category_suggestion=DeepSeekLanguageModel._optional_string(payload.get("category_suggestion")),
            semantic_score=semantic_score,
            reason=reason,
            summary=summary,
            discard_reason_summary=DeepSeekLanguageModel._optional_string(discard),
            link_summaries=link_summaries,
        )

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _link_summaries(value: object) -> tuple[AnalyzedLink, ...]:
        if not isinstance(value, list):
            return ()
        links: list[AnalyzedLink] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            url = DeepSeekLanguageModel._optional_string(item.get("url"))
            summary = DeepSeekLanguageModel._optional_string(item.get("summary"))
            if url and summary:
                links.append(AnalyzedLink(url=url, summary=summary[:240]))
        return tuple(links)

    @staticmethod
    def _require_link_summaries(email: FetchedEmail, analysis: SemanticAnalysis) -> None:
        required_links = set(report_links(list(email.extracted_links)))
        summarized_links = {item.url for item in analysis.link_summaries if item.summary.strip()}
        missing = required_links - summarized_links
        if missing:
            raise AnalysisValidationError("DeepSeek 未为全部有效链接提供用途摘要")

    @staticmethod
    def _complete_link_summaries(
        email: FetchedEmail,
        analysis: SemanticAnalysis,
    ) -> SemanticAnalysis:
        safe_links = report_links(list(email.extracted_links))
        summaries = {
            item.url: item.summary.strip()
            for item in analysis.link_summaries
            if item.url in safe_links and item.summary.strip()
        }
        completed = tuple(
            AnalyzedLink(
                url=url,
                summary=summaries.get(url)
                or urlsplit(url).hostname
                or "邮件链接",
            )
            for url in safe_links
        )
        return replace(analysis, link_summaries=completed)

    @staticmethod
    def _fallback_analysis(
        email: FetchedEmail,
        category_names: tuple[str, ...],
        error: AnalysisValidationError,
    ) -> SemanticAnalysis:
        category_name = (
            "其他"
            if "其他" in category_names
            else (category_names[0] if category_names else "其他")
        )
        subject = email.subject.strip() or "无主题邮件"
        body = " ".join(email.body_text.split())
        summary = subject if not body else f"{subject}：{body[:160]}"
        return SemanticAnalysis(
            source_suggestion=None,
            category_name=category_name,
            category_suggestion=None,
            semantic_score=0,
            reason=f"AI 分析暂时不可用，已使用基础信息保留邮件（{error}）。",
            summary=summary,
            discard_reason_summary=None,
            link_summaries=tuple(
                AnalyzedLink(
                    url=url,
                    summary=urlsplit(url).hostname or "邮件链接",
                )
                for url in report_links(list(email.extracted_links))
            ),
        )
