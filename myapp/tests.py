from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Account, Category, Ticket, TicketComment, Transaction, UserProfile


def make_user(username, role=UserProfile.ROLE_CUSTOMER, balance=0):
    user = User.objects.create_user(username, f'{username}@example.com', 'Pass@12345', first_name=username.title())
    user.profile.role = role
    user.profile.save()
    Account.objects.filter(user=user).update(balance=balance)
    return User.objects.get(pk=user.pk)  # fresh instance, no stale caches


class BaseTestCase(TestCase):
    def setUp(self):
        self.customer = make_user('cust', balance=100)
        self.other = make_user('other')
        self.agent = make_user('agent', UserProfile.ROLE_AGENT)
        self.agent2 = make_user('agent2', UserProfile.ROLE_AGENT)
        self.admin = make_user('boss', UserProfile.ROLE_ADMIN)
        self.category = Category.objects.create(name='Hardware')

    def new_ticket(self, reward=0, **kwargs):
        return services.create_ticket(
            Ticket(title='Broken laptop', description='It is broken', category=self.category, reward=reward, **kwargs),
            self.customer,
        )


class SignalTests(BaseTestCase):
    def test_new_user_gets_profile_and_wallet(self):
        u = User.objects.create_user('fresh', password='x')
        self.assertEqual(u.profile.role, UserProfile.ROLE_CUSTOMER)
        self.assertEqual(u.wallet.balance, 0)

    def test_superuser_defaults_to_admin_role(self):
        u = User.objects.create_superuser('root', 'r@example.com', 'x')
        self.assertEqual(u.profile.role, UserProfile.ROLE_ADMIN)


class WorkflowTests(BaseTestCase):
    def test_full_lifecycle_pays_reward(self):
        t = self.new_ticket(reward=40)
        services.take(t, self.agent)
        self.assertEqual(t.status, Ticket.STATUS_IN_PROGRESS)
        services.hold(t, self.agent, 'waiting on parts')
        services.resume(t, self.agent)
        services.resolve(t, self.agent, 'Replaced battery')
        self.assertEqual(t.status, Ticket.STATUS_RESOLVED)
        t = services.close(t, self.customer, 5, 'Great')
        self.assertEqual(t.status, Ticket.STATUS_CLOSED)
        self.assertEqual(t.rating, 5)
        self.assertEqual(Account.objects.get(user=self.customer).balance, 60)
        self.assertEqual(Account.objects.get(user=self.agent).balance, 40)
        self.assertTrue(Transaction.objects.filter(kind='reward', ticket=t, amount=40).exists())
        self.assertGreaterEqual(t.activities.count(), 6)

    def test_reopen_returns_to_same_agent(self):
        t = self.new_ticket()
        services.take(t, self.agent)
        services.resolve(t, self.agent, 'done')
        services.reopen(t, self.customer, 'still broken')
        self.assertEqual(t.status, Ticket.STATUS_REOPENED)
        self.assertEqual(t.assigned_to, self.agent)
        self.assertIsNone(t.resolved_at)
        self.assertTrue(t.comments.filter(body__contains='still broken').exists())

    def test_close_fails_without_funds_and_changes_nothing(self):
        t = self.new_ticket(reward=40)
        services.take(t, self.agent)
        services.resolve(t, self.agent, 'done')
        Account.objects.filter(user=self.customer).update(balance=10)
        with self.assertRaises(services.WorkflowError):
            services.close(t, self.customer)
        t.refresh_from_db()
        self.assertEqual(t.status, Ticket.STATUS_RESOLVED)
        self.assertEqual(Account.objects.get(user=self.agent).balance, 0)

    def test_customer_cannot_take_or_resolve(self):
        t = self.new_ticket()
        with self.assertRaises(services.WorkflowError):
            services.take(t, self.other)
        services.take(t, self.agent)
        with self.assertRaises(services.WorkflowError):
            services.resolve(t, self.customer, 'self-fixed')

    def test_other_agent_cannot_resolve_but_admin_can(self):
        t = self.new_ticket()
        services.take(t, self.agent)
        with self.assertRaises(services.WorkflowError):
            services.resolve(t, self.agent2, 'x')
        services.resolve(t, self.admin, 'fixed by admin')
        self.assertEqual(t.status, Ticket.STATUS_RESOLVED)

    def test_cannot_assign_to_customer_or_requester(self):
        t = self.new_ticket()
        with self.assertRaises(services.WorkflowError):
            services.assign(t, self.admin, self.other)
        with self.assertRaises(services.WorkflowError):
            services.assign(t, self.admin, self.customer)

    def test_release_returns_ticket_to_queue(self):
        t = self.new_ticket()
        services.take(t, self.agent)
        services.release(t, self.agent)
        self.assertIsNone(t.assigned_to)
        self.assertEqual(t.status, Ticket.STATUS_OPEN)

    def test_resolve_requires_resolution_text(self):
        t = self.new_ticket()
        services.take(t, self.agent)
        with self.assertRaises(services.WorkflowError):
            services.resolve(t, self.agent, '   ')

    def test_overdue(self):
        t = self.new_ticket()
        Ticket.objects.filter(pk=t.pk).update(due_date=timezone.localdate() - timedelta(days=1))
        t.refresh_from_db()
        self.assertTrue(t.is_overdue)

    def test_notifications_sent(self):
        t = self.new_ticket()
        services.assign(t, self.admin, self.agent)
        self.assertTrue(any('agent@example.com' in m.to for m in mail.outbox))


class ViewTests(BaseTestCase):
    def login(self, user):
        self.client.force_login(user)

    def test_login_required(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertRedirects(resp, reverse('login') + '?next=/')

    def test_register_creates_profile(self):
        resp = self.client.post(reverse('register'), {
            'first_name': 'New', 'last_name': 'Person', 'username': 'newbie', 'email': 'new@example.com',
            'password1': 'Str0ng!Passw0rd', 'password2': 'Str0ng!Passw0rd', 'city': 'Pune',
        })
        self.assertRedirects(resp, reverse('dashboard'))
        self.assertEqual(User.objects.get(username='newbie').profile.city, 'Pune')

    def test_register_shows_errors(self):
        resp = self.client.post(reverse('register'), {'username': 'x'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['form'].errors)

    def test_create_ticket(self):
        self.login(self.customer)
        resp = self.client.post(reverse('ticket_create'), {
            'title': 'Printer jam', 'description': 'Paper stuck', 'category': self.category.pk,
            'priority': 'high', 'reward': 10,
        })
        t = Ticket.objects.get(title='Printer jam')
        self.assertRedirects(resp, reverse('ticket_detail', args=[t.pk]))
        self.assertEqual(t.created_by, self.customer)

    def test_reward_cannot_exceed_balance(self):
        self.login(self.customer)
        resp = self.client.post(reverse('ticket_create'), {
            'title': 'X', 'description': 'Y', 'category': self.category.pk, 'priority': 'low', 'reward': 999,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('reward', resp.context['form'].errors)

    def test_customer_cannot_see_others_ticket(self):
        t = self.new_ticket()
        self.login(self.other)
        self.assertEqual(self.client.get(reverse('ticket_detail', args=[t.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('ticket_list')), t.title)

    def test_internal_notes_hidden_from_customer(self):
        t = self.new_ticket()
        TicketComment.objects.create(ticket=t, author=self.agent, body='SECRET NOTE', is_internal=True)
        self.login(self.customer)
        self.assertNotContains(self.client.get(reverse('ticket_detail', args=[t.pk])), 'SECRET NOTE')
        self.login(self.agent)
        self.assertContains(self.client.get(reverse('ticket_detail', args=[t.pk])), 'SECRET NOTE')

    def test_customer_cannot_post_internal_note(self):
        t = self.new_ticket()
        self.login(self.customer)
        self.client.post(reverse('ticket_comment', args=[t.pk]), {'body': 'hi', 'is_internal': 'on'})
        self.assertFalse(t.comments.get().is_internal)

    def test_actions_require_post(self):
        t = self.new_ticket()
        self.login(self.agent)
        self.assertEqual(self.client.get(reverse('ticket_action', args=[t.pk, 'take'])).status_code, 405)
        self.client.post(reverse('ticket_action', args=[t.pk, 'take']))
        t.refresh_from_db()
        self.assertEqual(t.assigned_to, self.agent)

    def test_edit_and_delete_permissions(self):
        t = self.new_ticket()
        self.login(self.other)
        self.assertEqual(self.client.get(reverse('ticket_edit', args=[t.pk])).status_code, 404)
        self.login(self.customer)
        self.client.post(reverse('ticket_delete', args=[t.pk]))
        self.assertFalse(Ticket.objects.filter(pk=t.pk).exists())

    def test_customer_cannot_delete_assigned_ticket(self):
        t = self.new_ticket()
        services.take(t, self.agent)
        self.login(self.customer)
        self.client.post(reverse('ticket_delete', args=[t.pk]))
        self.assertTrue(Ticket.objects.filter(pk=t.pk).exists())

    def test_admin_pages_restricted(self):
        self.login(self.agent)
        self.assertEqual(self.client.get(reverse('wallet_topup')).status_code, 403)
        self.assertEqual(self.client.get(reverse('user_list')).status_code, 403)

    def test_admin_topup_and_role_change(self):
        self.login(self.admin)
        self.client.post(reverse('wallet_topup'), {'user': self.other.pk, 'amount': 25})
        self.assertEqual(Account.objects.get(user=self.other).balance, 25)
        self.client.post(reverse('user_set_role', args=[self.other.pk]), {'role': 'agent'})
        self.assertEqual(UserProfile.objects.get(user=self.other).role, 'agent')

    def test_filters(self):
        self.new_ticket(priority='urgent')
        self.login(self.agent)
        resp = self.client.get(reverse('ticket_list'), {'priority': 'low'})
        self.assertEqual(resp.context['page'].paginator.count, 0)
        resp = self.client.get(reverse('ticket_list'), {'scope': 'unassigned', 'q': 'laptop'})
        self.assertEqual(resp.context['page'].paginator.count, 1)


class SeedCommandTests(TestCase):
    def test_seed_demo_and_every_page_renders(self):
        call_command('seed_demo', stdout=open('nul' if __import__('os').name == 'nt' else '/dev/null', 'w'))
        statuses = set(Ticket.objects.values_list('status', flat=True))
        self.assertEqual(statuses, {s for s, _ in Ticket.STATUS_CHOICES})
        for username in ('admin', 'priya', 'anita'):
            self.client.force_login(User.objects.get(username=username))
            for name in ('dashboard', 'ticket_list', 'ticket_create', 'profile', 'profile_edit', 'wallet', 'password_change'):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, (username, name))
            for t in Ticket.objects.all():
                code = self.client.get(reverse('ticket_detail', args=[t.pk])).status_code
                self.assertIn(code, (200, 404), (username, t.pk))


class TrendTests(BaseTestCase):
    def test_ranges(self):
        self.new_ticket()
        self.client.force_login(self.agent)
        expected_buckets = {'today': 24, '2d': 16, '7d': 7, '30d': 30}
        for key, n in expected_buckets.items():
            data = self.client.get(reverse('dashboard_trend'), {'range': key}).json()
            self.assertEqual(len(data['labels']), n, key)
            self.assertEqual(data['total_created'], 1, key)

    def test_custom_range(self):
        self.new_ticket()
        self.client.force_login(self.agent)
        today = timezone.localdate()
        data = self.client.get(reverse('dashboard_trend'), {
            'range': 'custom', 'from': (today - timedelta(days=9)).isoformat(), 'to': today.isoformat()}).json()
        self.assertEqual(len(data['labels']), 10)
        self.assertEqual(data['total_created'], 1)
        # Long ranges switch to weekly buckets.
        data = self.client.get(reverse('dashboard_trend'), {
            'range': 'custom', 'from': (today - timedelta(days=200)).isoformat(), 'to': today.isoformat()}).json()
        self.assertEqual(len(data['labels']), 29)

    def test_custom_range_validation(self):
        self.client.force_login(self.agent)
        today = timezone.localdate()
        for params in [
            {'range': 'custom', 'from': 'nope', 'to': today.isoformat()},
            {'range': 'custom', 'from': today.isoformat(), 'to': (today - timedelta(days=1)).isoformat()},
            {'range': 'custom', 'from': today.isoformat(), 'to': (today + timedelta(days=1)).isoformat()},
            {'range': 'custom', 'from': (today - timedelta(days=400)).isoformat(), 'to': today.isoformat()},
            {'range': 'bogus'},
        ]:
            self.assertEqual(self.client.get(reverse('dashboard_trend'), params).status_code, 400, params)

    def test_customer_only_counts_own_tickets(self):
        self.new_ticket()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('dashboard_trend')).json()['total_created'], 0)


class ActivityLogTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.new_ticket()
        services.take(self.ticket, self.agent)
        services.add_comment(self.ticket, self.agent, TicketComment(body='secret', is_internal=True))

    def test_staff_sees_everything(self):
        self.client.force_login(self.agent)
        resp = self.client.get(reverse('activity_log'))
        self.assertContains(resp, 'Added an internal note')
        self.assertContains(resp, 'Took the ticket')

    def test_customer_sees_own_tickets_without_internal_notes(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse('activity_log'))
        self.assertContains(resp, 'Took the ticket')
        self.assertNotContains(resp, 'Added an internal note')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('activity_log')), 'Took the ticket')

    def test_filters(self):
        self.client.force_login(self.agent)
        resp = self.client.get(reverse('activity_log'), {'kind': 'assigned'})
        self.assertEqual(resp.context['page'].paginator.count, 1)
        resp = self.client.get(reverse('activity_log'), {'actor': self.customer.pk})
        self.assertEqual(resp.context['page'].paginator.count, 1)  # "Ticket created"
        resp = self.client.get(reverse('activity_log'), {'q': self.ticket.number})
        self.assertEqual(resp.context['page'].paginator.count, 3)

    def test_csv_export_staff_only(self):
        self.client.force_login(self.agent)
        resp = self.client.get(reverse('activity_log'), {'export': 'csv'})
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('Took the ticket', resp.content.decode())
        self.client.force_login(self.customer)
        resp = self.client.get(reverse('activity_log'), {'export': 'csv'})
        self.assertEqual(resp['Content-Type'], 'text/html; charset=utf-8')


class TeamTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        t = self.new_ticket(reward=10)
        services.take(t, self.agent)
        services.resolve(t, self.agent, 'fixed')
        services.close(t, self.customer, 4)
        services.take(self.new_ticket(), self.agent)

    def test_customers_cannot_open_team_page(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('team')).status_code, 403)

    def test_team_stats(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('team'), {'period': 'all'})
        self.assertEqual(resp.status_code, 200)
        row = next(a for a in resp.context['agents'] if a == self.agent)
        self.assertEqual((row.active_n, row.resolved_n, row.rating_n, row.coins_earned), (1, 1, 1, 10))
        self.assertEqual(row.rating_avg, 4)
        self.assertIsNotNone(row.avg_resolution)
        self.assertEqual(resp.context['agents'][0], self.agent)  # busiest first
        self.assertEqual(resp.context['summary']['resolved'], 1)

    def test_search_and_sort(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('team'), {'q': 'agent2'})
        self.assertEqual([a.username for a in resp.context['agents']], ['agent2'])
        resp = self.client.get(reverse('team'), {'sort': 'name', 'period': 'bogus'})
        self.assertEqual(resp.context['period'], '30d')

    def test_dashboard_shows_four_agents(self):
        for i in range(4):
            make_user(f'extra{i}', UserProfile.ROLE_AGENT)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(len(resp.context['agents']), 4)
        self.assertEqual(resp.context['agents_total'], 7)  # agent, agent2, boss + 4 extra

    def test_ticket_list_assignee_filter(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('ticket_list'), {'assignee': self.agent.pk})
        self.assertEqual(resp.context['page'].paginator.count, 2)
        resp = self.client.get(reverse('ticket_list'), {'assignee': self.agent2.pk})
        self.assertEqual(resp.context['page'].paginator.count, 0)
        # Customers can't use it to see other people's tickets.
        self.client.force_login(self.other)
        resp = self.client.get(reverse('ticket_list'), {'assignee': self.agent.pk})
        self.assertEqual(resp.context['page'].paginator.count, 0)
