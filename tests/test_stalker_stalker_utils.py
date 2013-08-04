import unittest

class TestStatsdEvent(unittest.TestCase):
    def test___init__(self):
        # statsd_event = StatsdEvent(conf, logger, name_prepend)
        assert True # TODO: implement your test here

    def test_batch_gauge(self):
        # statsd_event = StatsdEvent(conf, logger, name_prepend)
        # self.assertEqual(expected, statsd_event.batch_gauge(metric_dict, prefix))
        assert True # TODO: implement your test here

    def test_counter(self):
        # statsd_event = StatsdEvent(conf, logger, name_prepend)
        # self.assertEqual(expected, statsd_event.counter(metric_name, value))
        assert True # TODO: implement your test here

    def test_timer(self):
        # statsd_event = StatsdEvent(conf, logger, name_prepend)
        # self.assertEqual(expected, statsd_event.timer(metric_name, duration))
        assert True # TODO: implement your test here

class TestGetBasicAuth(unittest.TestCase):
    def test_get_basic_auth(self):
        # self.assertEqual(expected, get_basic_auth(user, key))
        assert True # TODO: implement your test here

class TestGetLogger(unittest.TestCase):
    def test_get_logger(self):
        # self.assertEqual(expected, get_logger(name, log_path, level, count, fmt))
        assert True # TODO: implement your test here

class TestGetSyslogger(unittest.TestCase):
    def test_get_syslogger(self):
        # self.assertEqual(expected, get_syslogger(conf, name, log_to_console, log_route, fmt))
        assert True # TODO: implement your test here

class TestFileLikeLogger(unittest.TestCase):
    def test___init__(self):
        # file_like_logger = FileLikeLogger(logger)
        assert True # TODO: implement your test here

    def test_write(self):
        # file_like_logger = FileLikeLogger(logger)
        # self.assertEqual(expected, file_like_logger.write(message))
        assert True # TODO: implement your test here

class TestDaemon(unittest.TestCase):
    def test___init__(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        assert True # TODO: implement your test here

    def test_daemonize(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        # self.assertEqual(expected, daemon.daemonize())
        assert True # TODO: implement your test here

    def test_delpid(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        # self.assertEqual(expected, daemon.delpid())
        assert True # TODO: implement your test here

    def test_restart(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        # self.assertEqual(expected, daemon.restart(*args, **kw))
        assert True # TODO: implement your test here

    def test_start(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        # self.assertEqual(expected, daemon.start(*args, **kw))
        assert True # TODO: implement your test here

    def test_stop(self):
        # daemon = Daemon(pidfile, stdin, stdout, stderr)
        # self.assertEqual(expected, daemon.stop())
        assert True # TODO: implement your test here

class TestReadconf(unittest.TestCase):
    def test_readconf(self):
        # self.assertEqual(expected, readconf(conffile, section_name, log_name, defaults, raw))
        assert True # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()
