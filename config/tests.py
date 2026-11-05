from django.test import SimpleTestCase

from config.settings import leer_hosts


class LeerHostsTests(SimpleTestCase):
    def test_sin_variable_usa_los_hosts_locales(self):
        self.assertEqual(leer_hosts(None), ["127.0.0.1", "localhost"])

    def test_variable_vacia_usa_los_hosts_locales(self):
        self.assertEqual(leer_hosts(""), ["127.0.0.1", "localhost"])
        self.assertEqual(leer_hosts(" , "), ["127.0.0.1", "localhost"])

    def test_separa_por_comas_y_quita_espacios(self):
        self.assertEqual(
            leer_hosts(" 127.0.0.1 , localhost,,192.168.137.1 "),
            ["127.0.0.1", "localhost", "192.168.137.1"],
        )
