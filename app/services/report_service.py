import json
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.enums import ImportanceLevel
from app.core.link_policy import report_links
from app.infrastructure.models import EmailAnalysisModel, EmailModel, MailboxAccountModel
from app.infrastructure.persistence import (
    ClassificationRepository,
    EmailRepository,
    LocalReadMailRepository,
    ReportRepository,
)
from app.infrastructure.persistence.classification_repository import SOURCE_SEEDS


class ReportService:
    def __init__(
        self,
        report_repository: ReportRepository,
        email_repository: EmailRepository,
        read_mail_repository: LocalReadMailRepository,
        classification_repository: ClassificationRepository,
    ):
        self.report_repository = report_repository
        self.email_repository = email_repository
        self.read_mail_repository = read_mail_repository
        self.classification_repository = classification_repository

    def generate(
        self,
        scan_id: int,
        analyzed: list[tuple[EmailModel, EmailAnalysisModel]],
        failed_accounts: list[dict[str, str]],
    ):
        unique_emails = self._deduplicate(analyzed)
        marked_read_ids = self.read_mail_repository.marked_email_ids()
        unique_emails = [
            item
            for item in unique_emails
            if not set(getattr(item[0], "_report_email_ids", [item[0].id])).intersection(marked_read_ids)
        ]
        unique_emails.sort(key=self._sort_key)
        dates = [email.received_at or email.sent_at for email, _ in unique_emails]
        valid_dates = [date for date in dates if date is not None]
        earliest = min(valid_dates) if valid_dates else None
        latest = max(valid_dates) if valid_dates else None
        important_items = [
            (email, analysis)
            for email, analysis in unique_emails
            if analysis.importance == ImportanceLevel.IMPORTANT.value
        ]
        overview = self._overview(important_items, len(unique_emails))
        grouped: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        discardable: list[dict[str, object]] = []
        for email, analysis in unique_emails:
            item = self._snapshot_item(email, analysis)
            if analysis.importance == ImportanceLevel.DISCARDABLE.value:
                discardable.append(item)
            else:
                grouped[item["source_name"]][analysis.category_name].append(item)
        snapshot = {
            "time_range": {
                "earliest": self._iso(earliest),
                "latest": self._iso(latest),
            },
            "overview": overview,
            "tree": {
                source: {category: items for category, items in categories.items()}
                for source, categories in grouped.items()
            },
            "ordered_items": [
                self._snapshot_item(email, analysis)
                for email, analysis in unique_emails
                if analysis.importance != ImportanceLevel.DISCARDABLE.value
            ],
            "discardable": discardable,
            "failed_accounts": failed_accounts,
            "counts": {
                "unique": len(unique_emails),
                "important": len(important_items),
                "general": sum(
                    analysis.importance == ImportanceLevel.GENERAL.value
                    for _, analysis in unique_emails
                ),
                "discardable": len(discardable),
            },
        }
        return self.report_repository.create(scan_id, earliest, latest, overview, snapshot)

    @staticmethod
    def snapshot(report) -> dict[str, object]:
        return ReportService.prepare_snapshot(json.loads(report.snapshot_json))

    @staticmethod
    def prepare_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
        prepared = deepcopy(snapshot)
        tree = prepared.get("tree", {})
        if not isinstance(tree, dict):
            tree = {}

        tree_items = [
            item
            for categories in tree.values()
            if isinstance(categories, dict)
            for category_items in categories.values()
            if isinstance(category_items, list)
            for item in category_items
            if isinstance(item, dict)
        ]
        ordered_items = prepared.get("ordered_items")
        is_legacy = not isinstance(ordered_items, list)
        items = tree_items if is_legacy else ordered_items
        items_to_prepare = tree_items if is_legacy else [*items, *tree_items]
        for item in items_to_prepare:
            item["links"] = ReportService._compatible_links(item.get("links", []))
            if is_legacy:
                item["source_name"] = ReportService._compatible_source_name(
                    item.get("sender_address")
                )
        discardable = prepared.get("discardable", [])
        if isinstance(discardable, list):
            for item in discardable:
                if isinstance(item, dict):
                    item["links"] = ReportService._compatible_links(item.get("links", []))

        if is_legacy:
            prepared["tree"] = ReportService._rebuild_tree(tree_items)
        prepared["ordered_items"] = sorted(items, key=ReportService._snapshot_sort_key)
        return prepared

    @staticmethod
    def _rebuild_tree(items: list[dict[str, object]]) -> dict[str, dict[str, list[dict[str, object]]]]:
        tree: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for item in items:
            source_name = str(item.get("source_name") or "未知来源")
            category_name = str(item.get("category_name") or "其他")
            tree[source_name][category_name].append(item)
        return {
            source: {category: category_items for category, category_items in categories.items()}
            for source, categories in tree.items()
        }

    @staticmethod
    def _compatible_links(value: object) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        raw_urls = [
            item.get("url") if isinstance(item, dict) else item
            for item in value
        ]
        safe_urls = report_links([url for url in raw_urls if isinstance(url, str)])
        summaries = {
            safe_url: item.get("summary", "").strip()
            for item in value
            if isinstance(item, dict) and isinstance(item.get("url"), str)
            for safe_url in report_links([item["url"]])
            if isinstance(item.get("summary"), str) and item.get("summary", "").strip()
        }
        links: list[dict[str, str]] = []
        for safe_url in safe_urls:
            links.append(
                {
                    "url": safe_url,
                    "summary": summaries.get(safe_url) or urlsplit(safe_url).hostname or safe_url,
                }
            )
        return links

    @staticmethod
    def _compatible_source_name(sender_address: object) -> str:
        if not isinstance(sender_address, str) or "@" not in sender_address:
            return "未知来源"
        domain = sender_address.rsplit("@", 1)[-1].strip().lower()
        for source_name, match_type, pattern in SOURCE_SEEDS:
            if match_type == "domain" and (domain == pattern or domain.endswith(f".{pattern}")):
                return source_name
        return domain or "未知来源"

    @staticmethod
    def _snapshot_sort_key(item: dict[str, object]) -> tuple[int, float]:
        rank = {"important": 0, "general": 1, "discardable": 2}
        raw_date = item.get("received_at") or item.get("sent_at")
        timestamp = 0.0
        if isinstance(raw_date, str):
            try:
                timestamp = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        return rank.get(str(item.get("importance")), 3), -timestamp

    def _deduplicate(
        self,
        analyzed: list[tuple[EmailModel, EmailAnalysisModel]],
    ) -> list[tuple[EmailModel, EmailAnalysisModel]]:
        groups: dict[str, list[tuple[EmailModel, EmailAnalysisModel]]] = defaultdict(list)
        for item in analyzed:
            groups[item[0].duplicate_group_key].append(item)
        members = self.email_repository.duplicate_members(set(groups))
        stored_members: dict[str, list[EmailModel]] = defaultdict(list)
        for member in members:
            stored_members[member.duplicate_group_key].append(member)
        unique: list[tuple[EmailModel, EmailAnalysisModel]] = []
        for items in groups.values():
            primary_email, primary_analysis = items[0]
            group_members = stored_members[primary_email.duplicate_group_key]
            primary_email._report_account_names = list(
                dict.fromkeys(member.account.name for member in group_members)
            )
            primary_email._report_email_ids = [member.id for member in group_members]
            unique.append((primary_email, primary_analysis))
        return unique

    @staticmethod
    def _overview(
        important_items: list[tuple[EmailModel, EmailAnalysisModel]],
        total_count: int,
    ) -> str:
        if not important_items:
            return f"本次共整理 {total_count} 封邮件，没有邮件达到“重要”阈值。"
        summaries = "；".join(analysis.summary for _, analysis in important_items)
        return f"有 {len(important_items)} 封重要邮件建议亲自审核：{summaries}"

    def _snapshot_item(self, email: EmailModel, analysis: EmailAnalysisModel) -> dict[str, object]:
        source_name = self.classification_repository.display_source_name(email.sender_address)
        link_summaries = [
            {"url": item.url, "summary": item.summary}
            for item in analysis.link_summaries
        ]
        return {
            "email_id": email.id,
            "duplicate_email_ids": getattr(email, "_report_email_ids", [email.id]),
            "account_names": getattr(email, "_report_account_names", [email.account.name]),
            "subject": email.subject,
            "sender_name": email.sender_name,
            "sender_address": email.sender_address,
            "sent_at": ReportService._iso(email.sent_at),
            "received_at": ReportService._iso(email.received_at),
            "source_name": source_name,
            "category_name": analysis.category_name,
            "importance": analysis.importance,
            "summary": analysis.summary,
            "discard_reason_summary": analysis.discard_reason_summary,
            "links": link_summaries,
            "mail_url": f"/mail/{email.id}",
        }

    @staticmethod
    def _sort_key(item: tuple[EmailModel, EmailAnalysisModel]):
        email, analysis = item
        rank = {
            ImportanceLevel.IMPORTANT.value: 0,
            ImportanceLevel.GENERAL.value: 1,
            ImportanceLevel.DISCARDABLE.value: 2,
        }
        received = email.received_at or email.sent_at or datetime.min
        if received.tzinfo is not None:
            received = received.replace(tzinfo=None)
        seconds = (
            received.toordinal() * 86400
            + received.hour * 3600
            + received.minute * 60
            + received.second
        )
        return rank.get(analysis.importance, 3), -seconds

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
