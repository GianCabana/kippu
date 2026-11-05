from django.conf import settings
from django.test import SimpleTestCase

from config.settings import leer_booleano, leer_hosts


class LeerBooleanoTests(SimpleTestCase):
    def test_sin_variable_queda_apagado(self):
        self.assertFalse(leer_booleano(None))
        self.assertFalse(leer_booleano(""))

    def test_valores_que_encienden(self):
        for valor in ("True", "true", " TRUE ", "1", "si", "Sí", "yes", "on"):
            with self.subTest(valor=valor):
                self.assertTrue(leer_booleano(valor))

    def test_cualquier_otro_valor_queda_apagado(self):
        for valor in ("False", "false", "0", "no", "off", "verdadero", "debug"):
            with self.subTest(valor=valor):
                self.assertFalse(leer_booleano(valor))


class EstaticosTests(SimpleTestCase):
    def test_whitenoise_va_justo_despues_de_security(self):
        posicion = settings.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
        self.assertEqual(settings.MIDDLEWARE[posicion + 1], "whitenoise.middleware.WhiteNoiseMiddleware")

    def test_collectstatic_tiene_destino(self):
        self.assertEqual(settings.STATIC_ROOT, settings.BASE_DIR / "staticfiles")


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
