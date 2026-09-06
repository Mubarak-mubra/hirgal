from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from accounting.services import seed_default_chart_of_accounts


class Command(BaseCommand):
    help = "Ku dar xisaabaha caadiga ah (Default Chart of Accounts)"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, nargs="?", help="Magaca isticmaalaha (optional: leave blank for all users)")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options.get("username")

        if username:
            users = User.objects.filter(username=username)
            if not users.exists():
                self.stdout.write(self.style.ERROR(f"User '{username}' ma jiro"))
                return
        else:
            users = User.objects.all()

        total_created = 0
        for user in users:
            created = seed_default_chart_of_accounts(user)
            total_created += created
            self.stdout.write(self.style.SUCCESS(f"User '{user.username}': xisaabo {created} ah ayaa la ku daray"))

        self.stdout.write(self.style.SUCCESS(f"Gudigaa: xisaabo {total_created} ah ayaa la ku daray"))
