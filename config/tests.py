import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from config.settings import ajustes_https, leer_booleano, leer_hosts, origen


class OrigenTests(SimpleTestCase):
    def test_deja_solo_esquema_y_host(self):
        self.assertEqual(origen("https://kippurestaurant.com/"), "https://kippurestaurant.com")
        self.assertEqual(origen("https://kippurestaurant.com/mesa/abc"), "https://kippurestaurant.com")

    def test_conserva_el_puerto_local(self):
        self.assertEqual(origen("http://192.168.1.5:8000"), "http://192.168.1.5:8000")


class ServirMediaTests(SimpleTestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.media = Path(carpeta.name)
        (self.media / "productos").mkdir()
        (self.media / "productos" / "foto.jpg").write_bytes(b"jpg")
        (self.media.parent / "fuera.txt").write_bytes(b"secreto")
        self.addCleanup((self.media.parent / "fuera.txt").unlink)

    def pedir(self, ruta, **ajustes):
        """Devuelve (código, contenido, Cache-Control) y cierra el archivo (en Windows queda tomado si no)."""
        with override_settings(MEDIA_ROOT=self.media, **ajustes):
            respuesta = self.client.get("/media/" + ruta)
        contenido = b"".join(respuesta.streaming_content) if respuesta.streaming else respuesta.content
        respuesta.close()
        return respuesta.status_code, contenido, respuesta.get("Cache-Control", "")

    def test_apagado_en_la_web_no_sirve_fotos(self):
        codigo, _, _ = self.pedir("productos/foto.jpg", DEBUG=False, SERVIR_MEDIA=False)

        self.assertEqual(codigo, 404)

    def test_con_la_variable_sirve_fotos(self):
        codigo, contenido, cache = self.pedir("productos/foto.jpg", DEBUG=False, SERVIR_MEDIA=True)

        self.assertEqual(codigo, 200)
        self.assertEqual(contenido, b"jpg")
        self.assertIn("max-age", cache)

    def test_en_desarrollo_sirve_fotos(self):
        codigo, _, _ = self.pedir("productos/foto.jpg", DEBUG=True, SERVIR_MEDIA=False)

        self.assertEqual(codigo, 200)

    def test_no_sale_de_media(self):
        for ruta in ("../fuera.txt", "..%2Ffuera.txt", "productos/../../fuera.txt"):
            with self.subTest(ruta=ruta):
                codigo, contenido, _ = self.pedir(ruta, DEBUG=False, SERVIR_MEDIA=True)
                self.assertIn(codigo, (400, 404))
                self.assertNotIn(b"secreto", contenido)


class AjustesHttpsTests(SimpleTestCase):
    def test_apagado_no_cambia_nada(self):
        self.assertEqual(ajustes_https(False), {})

    def test_encendido_cumple_check_deploy(self):
        ajustes = ajustes_https(True)

        self.assertTrue(ajustes["SECURE_SSL_REDIRECT"])
        self.assertTrue(ajustes["SESSION_COOKIE_SECURE"])
        self.assertTrue(ajustes["CSRF_COOKIE_SECURE"])
        self.assertGreater(ajustes["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(ajustes["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))


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
