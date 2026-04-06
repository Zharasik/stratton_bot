from __future__ import annotations

import csv
from pathlib import Path

from stratton_bot.domain.entities import UserProfile


class UserCsvExporter:
    def export(self, users: list[UserProfile], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "Username", "Full Name", "Status", "Retries", "Registered At"])
            for user in users:
                writer.writerow(
                    [
                        user.user_id,
                        user.username or "",
                        user.full_name or "",
                        user.status,
                        user.retry_count,
                        user.registered_at.isoformat(sep=" ") if user.registered_at else "",
                    ]
                )
        return output_path
