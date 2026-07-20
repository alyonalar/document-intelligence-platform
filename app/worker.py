import argparse
import time

from sqlmodel import Session

from app.db.engine import engine
from app.services.processing_jobs import process_next_queued_job


def run_once() -> int:
    with Session(engine) as session:
        job = process_next_queued_job(session)
        if not job:
            print("No queued jobs.")
            return 0

        print(f"Processed job {job.id}: {job.status} - {job.message or ''}")
        return 1


def run_loop(interval: float) -> None:
    print(f"Worker started. Polling every {interval} second(s).")
    while True:
        processed = run_once()
        if not processed:
            time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued document intelligence jobs.")
    parser.add_argument("--loop", action="store_true", help="Continuously poll for queued jobs.")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval for --loop.")
    args = parser.parse_args()

    if args.loop:
        run_loop(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
