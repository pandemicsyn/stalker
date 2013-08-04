import unittest

class TestPagerDuty(unittest.TestCase):
    def test___init__(self):
        # pager_duty = PagerDuty(conf, logger, redis_client)
        assert True # TODO: implement your test here

    def test_clear(self):
        # pager_duty = PagerDuty(conf, logger, redis_client)
        # self.assertEqual(expected, pager_duty.clear(check))
        assert True # TODO: implement your test here

    def test_fail(self):
        # pager_duty = PagerDuty(conf, logger, redis_client)
        # self.assertEqual(expected, pager_duty.fail(check))
        assert True # TODO: implement your test here

class TestMailgun(unittest.TestCase):
    def test___init__(self):
        # mailgun = Mailgun(conf, logger, redis_client)
        assert True # TODO: implement your test here

    def test_clear(self):
        # mailgun = Mailgun(conf, logger, redis_client)
        # self.assertEqual(expected, mailgun.clear(check))
        assert True # TODO: implement your test here

    def test_fail(self):
        # mailgun = Mailgun(conf, logger, redis_client)
        # self.assertEqual(expected, mailgun.fail(check))
        assert True # TODO: implement your test here

class TestEmailNotify(unittest.TestCase):
    def test___init__(self):
        # email_notify = EmailNotify(conf, logger, redis_client)
        assert True # TODO: implement your test here

    def test_clear(self):
        # email_notify = EmailNotify(conf, logger, redis_client)
        # self.assertEqual(expected, email_notify.clear(check))
        assert True # TODO: implement your test here

    def test_fail(self):
        # email_notify = EmailNotify(conf, logger, redis_client)
        # self.assertEqual(expected, email_notify.fail(check))
        assert True # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()
