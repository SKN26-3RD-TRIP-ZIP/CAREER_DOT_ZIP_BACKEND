import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.external.services.mock_jobs_service import (
    DEFAULT_COUNT,
    DEFAULT_SEED,
    GENERATED_DATA_FILE,
    MockJobsService,
    generate_mock_jobs,
)


class Command(BaseCommand):
    help = "Generate deterministic CAREER_ZIP_MOCK synthetic job data for QA."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
        parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
        parser.add_argument(
            "--output",
            default=str(GENERATED_DATA_FILE),
            help="Output JSON path. Defaults to ignored local generated data file.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        count = options["count"]
        seed = options["seed"]
        output = Path(options["output"])
        jobs = generate_mock_jobs(count=count, seed=seed)

        payload = {
            "source": "CAREER_ZIP_MOCK",
            "is_mock": True,
            "count": len(jobs),
            "seed": seed,
            "jobs": jobs,
        }

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Generated {len(jobs)} CAREER_ZIP_MOCK jobs in memory (seed={seed})."
                )
            )
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

        MockJobsService.reload()
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(jobs)} CAREER_ZIP_MOCK jobs to {output} (seed={seed})."
            )
        )
