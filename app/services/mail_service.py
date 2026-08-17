import json

from app.infrastructure.persistence import (
    ClassificationRepository,
    EmailRepository,
    latest_analysis,
    parse_json_list,
)


class MailService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_detail(self, email_id: int) -> dict:
        with self.session_factory() as session:
            email = EmailRepository(session).get_detail(email_id)
            analysis = latest_analysis(email)
            return {
                "id": email.id,
                "account": {
                    "id": email.account.id,
                    "name": email.account.name,
                    "email_address": email.account.email_address,
                },
                "subject": email.subject,
                "sender_name": email.sender_name,
                "sender_address": email.sender_address,
                "recipients": json.loads(email.recipients_json),
                "sent_at": email.sent_at,
                "received_at": email.received_at,
                "body_text": email.body_text,
                "attachment_names": json.loads(email.attachment_names_json),
                "attachment_count": email.attachment_count,
                "links": parse_json_list(email.extracted_links_json),
                "link_summaries": [
                    {"url": item.url, "summary": item.summary}
                    for item in analysis.link_summaries
                ],
                "analysis": {
                    "version": analysis.version,
                    "source_name": ClassificationRepository(session).display_source_name(
                        email.sender_address
                    ),
                    "category_name": analysis.category_name,
                    "importance": analysis.importance,
                    "rule_score": analysis.rule_score,
                    "semantic_score": analysis.semantic_score,
                    "total_score": analysis.total_score,
                    "reason": analysis.ai_reason,
                    "summary": analysis.summary,
                    "discard_reason_summary": analysis.discard_reason_summary,
                    "rule_hits": [
                        {
                            "code": item.rule_code,
                            "description": item.description,
                            "score": item.score,
                        }
                        for item in analysis.score_details
                    ],
                },
            }
