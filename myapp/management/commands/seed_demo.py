"""
Load demo data so every helpdesk feature can be tried right away.

    python manage.py seed_demo           # create demo users + tickets (only if no tickets exist)
    python manage.py seed_demo --reset   # wipe all tickets/transactions and recreate the demo set
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction as db_transaction
from django.test.utils import override_settings
from django.utils import timezone

from myapp import services
from myapp.permissions import get_profile
from myapp.models import Account, Category, Ticket, TicketActivity, TicketComment, Transaction, UserProfile

ADMIN_PASSWORD = 'Admin@123'
DEMO_PASSWORD = 'Demo@1234'

USERS = [
    # username, first, last, role, department, city, state
    ('admin', 'Site', 'Admin', UserProfile.ROLE_ADMIN, 'IT Management', 'Bengaluru', 'Karnataka'),
    ('priya', 'Priya', 'Sharma', UserProfile.ROLE_AGENT, 'IT Support', 'Pune', 'Maharashtra'),
    ('rahul', 'Rahul', 'Verma', UserProfile.ROLE_AGENT, 'Network Operations', 'Delhi', 'Delhi'),
    ('anita', 'Anita', 'Desai', UserProfile.ROLE_CUSTOMER, 'Finance', 'Mumbai', 'Maharashtra'),
    ('vikram', 'Vikram', 'Singh', UserProfile.ROLE_CUSTOMER, 'Sales', 'Jaipur', 'Rajasthan'),
    ('neha', 'Neha', 'Gupta', UserProfile.ROLE_CUSTOMER, 'Human Resources', 'Chennai', 'Tamil Nadu'),
]

CATEGORIES = [
    ('Hardware', 'Laptops, desktops, printers, peripherals'),
    ('Software', 'Applications, installs, licences, crashes'),
    ('Network', 'Wi-Fi, VPN, shared drives, connectivity'),
    ('Account & Access', 'Logins, passwords, permissions, onboarding'),
    ('Email', 'Outlook, mailboxes, calendars, signatures'),
    ('Billing & Payroll', 'Payroll portal, invoices, reimbursements'),
]

# Each ticket: (requester, title, category, priority, created N days ago, due in N days (None = no due date),
#               reward, description, steps). Steps are applied in order through the real workflow.
TICKETS = [
    ('anita', "Laptop won't power on after Windows update", 'Hardware', 'urgent', 4, -2, 50,
     'My Dell Latitude installed an update last night and now it will not turn on. The charging light blinks amber '
     'three times. I have a client presentation tomorrow.', []),
    ('vikram', 'Cannot access shared drive S:', 'Network', 'high', 1, 2, 30,
     'Since this morning the S: drive shows a red X and I get "Network path not found".',
     [('comment', 'vikram', 'Error code shown is 0x80070035, in case that helps.')]),
    ('neha', 'New employee account for Kiran Rao', 'Account & Access', 'medium', 2, 5, 0,
     'Kiran Rao joins HR on Monday. Please create an AD account, email and access to the HRMS portal.',
     [('assign', 'admin', 'rahul'),
      ('comment', 'rahul', 'Account created. Waiting for the HRMS licence before I can grant portal access.')]),
    ('anita', 'Outlook keeps asking for my password', 'Email', 'high', 3, 1, 40,
     'Outlook prompts for my password every few minutes even though I enter it correctly.',
     [('take', 'priya'),
      ('comment', 'priya', 'Did you change your password recently? Can you also tell me your Outlook version (File > Office Account)?'),
      ('comment', 'anita', 'Yes, I changed it last Friday. Version is Microsoft 365, build 2409.'),
      ('note', 'priya', 'Likely stale credentials in Credential Manager. Will clear them on a remote session.')]),
    ('vikram', 'VPN disconnects every 10 minutes', 'Network', 'high', 6, -1, 60,
     'When working from home the VPN drops every ~10 minutes and I lose my CRM session.',
     [('take', 'rahul'),
      ('comment', 'rahul', 'Collected logs. The drops line up with your ISP renewing the IP lease.'),
      ('hold', 'rahul', 'Waiting for ISP to confirm a fix on their side')]),
    ('neha', 'Printer on 3rd floor printing blank pages', 'Hardware', 'low', 3, 3, 20,
     'The HP printer near HR prints blank pages for every job.',
     [('take', 'priya'),
      ('resolve', 'priya', 'The toner cartridge was empty and the low-toner warning was disabled. Replaced the cartridge and re-enabled alerts.')]),
    ('anita', 'Excel crashes when opening large files', 'Software', 'medium', 8, 4, 25,
     'Excel freezes and closes when I open the monthly finance workbook (about 80 MB).',
     [('take', 'rahul'),
      ('resolve', 'rahul', 'Upgraded Office from 32-bit to 64-bit so Excel can use more memory.'),
      ('reopen', 'anita', 'The file opens now, but Excel still crashes when I refresh the pivot tables.')]),
    ('vikram', 'Install Adobe Acrobat Pro', 'Software', 'low', 10, None, 15,
     'I need Acrobat Pro to edit and sign customer contracts.',
     [('take', 'priya'),
      ('resolve', 'priya', 'Installed Acrobat Pro and assigned you a licence from the pool.'),
      ('close', 'vikram', 5, 'Quick and painless, thank you!')]),
    ('neha', 'Payroll portal shows wrong leave balance', 'Billing & Payroll', 'medium', 12, None, 0,
     'My leave balance shows 2 days but it should be 9 days.',
     [('assign', 'admin', 'rahul'),
      ('comment', 'rahul', 'The nightly sync from HRMS failed on the 1st. Re-running it now.'),
      ('resolve', 'rahul', 'Re-ran the HRMS sync job. Balance now shows 9 days.'),
      ('close', 'neha', 4, 'Fixed, but it took a couple of days.')]),
    ('anita', 'Forgot ERP password', 'Account & Access', 'urgent', 5, None, 10,
     'Locked out of the ERP after too many attempts. Need to approve invoices today.',
     [('take', 'priya'),
      ('resolve', 'priya', 'Unlocked the account and sent a temporary password by SMS.'),
      ('close', 'anita', 5, 'Super quick!')]),
    ('vikram', 'Mouse is double-clicking', 'Hardware', 'low', 0, None, 0,
     'My wireless mouse registers two clicks for every single click.', []),
    ('neha', 'Wi-Fi very slow in conference room B', 'Network', 'medium', 7, -3, 35,
     'Video calls in conference room B keep freezing. Speed test shows under 2 Mbps.',
     [('take', 'priya'),
      ('note', 'priya', 'Access point AP-3B is on an old firmware. Need a maintenance window to upgrade.')]),
    ('anita', 'Request a second monitor', 'Hardware', 'low', 15, None, 0,
     'I would like a second monitor to work with spreadsheets side by side.',
     [('take', 'rahul'),
      ('resolve', 'rahul', 'Delivered and connected a 24" Dell monitor.'),
      ('close', 'anita', 3, 'Works well, but it took over a week to arrive.')]),
    ('priya', 'Need admin rights to install a diagnostic tool', 'Account & Access', 'medium', 2, 3, 0,
     'I need temporary local admin rights on my laptop to install a network diagnostic tool.',
     [('take', 'rahul')]),
    ('vikram', 'Email signature not showing company logo', 'Email', 'low', 1, 7, 5,
     'The logo in my email signature shows as a broken image for external recipients.', []),
]


class Command(BaseCommand):
    help = 'Create demo users, categories and tickets covering every status of the helpdesk workflow.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete all tickets and transactions first.')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')  # keep output quiet
    def handle(self, *args, **options):
        with db_transaction.atomic():
            users = self.create_users()
            categories = self.create_categories()

            if options['reset']:
                Ticket.objects.all().delete()
                Transaction.objects.all().delete()
                Account.objects.update(balance=0)
                # Restart numbering so the demo tickets are HD-00001 … HD-00015 again.
                tables = [{'table': m._meta.db_table, 'column': 'id'}
                          for m in (Ticket, TicketComment, TicketActivity, Transaction)]
                with connection.cursor() as cursor:
                    for sql in connection.ops.sequence_reset_by_name_sql(no_style(), tables):
                        cursor.execute(sql)
                self.stdout.write('Removed existing tickets and transactions.')
            elif Ticket.objects.exists():
                self.stdout.write(self.style.WARNING(
                    'Tickets already exist, so no demo tickets were added. Use --reset to recreate them.'))
                self.print_logins()
                return

            for username in ('anita', 'vikram', 'neha', 'priya'):
                services.top_up(users[username], 500, users['admin'], 'Welcome bonus')
            Transaction.objects.update(created_at=timezone.now() - timedelta(days=20))

            for spec in TICKETS:
                self.create_ticket(users, categories, *spec)

        self.stdout.write(self.style.SUCCESS(f'Created {len(TICKETS)} demo tickets.'))
        self.print_logins()

    def create_users(self):
        users = {}
        for username, first, last, role, dept, city, state in USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.first_name, user.last_name = first, last
            user.email = f'{username}@example.com'
            user.is_staff = user.is_superuser = (role == UserProfile.ROLE_ADMIN)
            user.set_password(ADMIN_PASSWORD if role == UserProfile.ROLE_ADMIN else DEMO_PASSWORD)
            user.save()
            profile = get_profile(user)
            profile.role, profile.department, profile.city, profile.state = role, dept, city, state
            profile.phone = '+91 98' + str(sum(map(ord, username)) * 104729 % 10**8).zfill(8)
            profile.address = '12 MG Road'
            profile.save()
            Account.objects.get_or_create(user=user)
            users[username] = user
        return users

    def create_categories(self):
        return {name: Category.objects.update_or_create(name=name, defaults={'description': desc})[0]
                for name, desc in CATEGORIES}

    def create_ticket(self, users, categories, requester, title, category, priority, days_ago, due_in,
                      reward, description, steps):
        now = timezone.now()
        today = timezone.localdate()
        start = now - timedelta(days=days_ago, hours=3)
        # Spread the ticket's events between its creation time and now.
        gap = (now - start) / (len(steps) + 1)

        ticket = services.create_ticket(Ticket(
            title=title, description=description, category=categories[category], priority=priority,
            reward=reward, due_date=(today + timedelta(days=due_in)) if due_in is not None else None,
        ), users[requester])

        clock = start
        self._stamp(ticket, clock)
        for step in steps:
            clock += gap
            kind, actor = step[0], users[step[1]]
            ticket.refresh_from_db()
            if kind == 'take':
                services.take(ticket, actor)
            elif kind == 'assign':
                services.assign(ticket, actor, users[step[2]])
            elif kind in ('comment', 'note'):
                services.add_comment(ticket, actor, TicketComment(body=step[2], is_internal=(kind == 'note')))
            elif kind == 'hold':
                services.hold(ticket, actor, step[2])
            elif kind == 'resolve':
                services.resolve(ticket, actor, step[2])
                Ticket.objects.filter(pk=ticket.pk).update(resolved_at=clock)
            elif kind == 'reopen':
                services.reopen(ticket, actor, step[2])
            elif kind == 'close':
                services.close(ticket, actor, step[2], step[3])
                Ticket.objects.filter(pk=ticket.pk).update(closed_at=clock)
                Transaction.objects.filter(ticket=ticket).update(created_at=clock)
            self._stamp(ticket, clock)

        Ticket.objects.filter(pk=ticket.pk).update(created_at=start, updated_at=clock)

    @staticmethod
    def _stamp(ticket, when):
        """Backdate events that were just created (they still carry the real 'now' timestamp)."""
        recent = timezone.now() - timedelta(minutes=5)
        TicketActivity.objects.filter(ticket=ticket, created_at__gte=recent).update(created_at=when)
        TicketComment.objects.filter(ticket=ticket, created_at__gte=recent).update(created_at=when)

    def print_logins(self):
        self.stdout.write('\nDemo logins:')
        self.stdout.write(f'  Admin     admin                 / {ADMIN_PASSWORD}')
        self.stdout.write(f'  Agents    priya, rahul          / {DEMO_PASSWORD}')
        self.stdout.write(f'  Customers anita, vikram, neha   / {DEMO_PASSWORD}')
