import json

from django.core.management.base import BaseCommand, CommandError

from quotes.tariff_versions import TariffChangeError, count_rows, create_tariff_version


class Command(BaseCommand):
    help = (
        "Create a new tariff version by copying the current one and applying a JSON change file "
        "that lists only the values to change. Nothing is created if the file is not valid."
    )

    def add_arguments(self, parser):
        parser.add_argument("label", help="Label of the new version, for example RATES-2026-2.")
        parser.add_argument(
            "change_file",
            help='JSON file, for example {"mid": {"fees": {"liftgate": "90.00"}}}.',
        )

    def handle(self, *args, label, change_file, **options):
        try:
            with open(change_file, encoding="utf-8") as handle:
                changes = json.load(handle)
        except OSError as error:
            raise CommandError(f"Cannot read {change_file}: {error}") from error
        except json.JSONDecodeError as error:
            raise CommandError(f"{change_file} is not valid JSON: {error}") from error
        try:
            version = create_tariff_version(label, changes)
        except TariffChangeError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Created tariff version {version.label} ({count_rows(version)} rows). "
                "It is now the current version."
            )
        )
