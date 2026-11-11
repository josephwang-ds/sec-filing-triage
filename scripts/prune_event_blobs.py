"""Delete superseded event checkpoints from the Blob store. Dry run unless --apply."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

from company_lens.events.blob_store import (
    BlobRequestError,
    HttpBlobTransport,
    prune_checkpoints,
)
from company_lens.events.run import read_failure_reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete. Without this nothing is removed.",
    )
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=24.0,
        help="Never delete a checkpoint uploaded more recently than this.",
    )
    parser.add_argument(
        "--keep-newest",
        type=int,
        default=None,
        help=(
            "Do not read the commit record; keep the N most recently uploaded "
            "checkpoints instead. Only for a store whose content reads are refused."
        ),
    )
    parser.add_argument(
        "--drill",
        action="store_true",
        help="Use EVENTS_DRILL_BLOB_READ_WRITE_TOKEN and the drill prefix.",
    )
    parser.add_argument("--now", default=None, help="ISO timestamp for a test; default is now")
    args = parser.parse_args(argv)

    if args.min_age_hours < 0:
        print("config_error=min_age_negative")
        return 2
    if args.keep_newest is not None and args.keep_newest < 1:
        print("config_error=keep_newest_below_one")
        return 2
    if args.drill:
        os.environ["EVENTS_BLOB_PREFIX"] = "lens-events-drill"
    token = os.environ.get(
        "EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" if args.drill else "BLOB_READ_WRITE_TOKEN", ""
    ).strip()
    if not token:
        print("config_error=blob_missing")
        return 2
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    try:
        report = prune_checkpoints(
            open_transport(token),
            now=now,
            min_age=timedelta(hours=args.min_age_hours),
            keep_newest=args.keep_newest,
            apply=args.apply,
        )
    except (BlobRequestError, OSError, ValueError) as exc:
        # The pointer could not be read, so nothing was deleted. Same code and
        # the same reason line as a failed checkpoint read on the refresh path.
        print(f"prune=failed {read_failure_reason(exc)}")
        return 3

    for row in report["kept"]:
        print(
            f"checkpoint action=keep reason={row['reason']} size={row['size']} "
            f"uploaded_at={row['uploaded_at']} pathname={row['pathname']}"
        )
    verb = "delete" if report["applied"] else "would_delete"
    for row in report["deleted"]:
        print(
            f"checkpoint action={verb} size={row['size']} "
            f"uploaded_at={row['uploaded_at']} pathname={row['pathname']}"
        )
    print(
        f"prune={report['status']} mode={report['mode']} listed={report['listed']} "
        f"listed_bytes={report['listed_bytes']} kept={len(report['kept'])} "
        f"{'deleted' if report['applied'] else 'would_delete'}={len(report['deleted'])} "
        f"freed_bytes={report['freed_bytes']}"
    )
    # The pointer names an object the listing does not have. That is a store
    # worth looking at, not a sweep that went well.
    return 3 if report["status"] == "pointer_not_listed" else 0


def open_transport(token: str):
    """Tests replace this."""
    return HttpBlobTransport(token)


if __name__ == "__main__":
    sys.exit(main())
