from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LoginPersonalTests(TestCase):
    def setUp(self):
        self.url = reverse('admin:login')
        self.caja = reverse('pedidos:caja')
        modelo = get_user_model()
        self.personal = modelo.objects.create_user(username='personal_login', password='Pruebas123!', is_staff=True)
        self.cliente = modelo.objects.create_user(username='cliente_login', password='Pruebas123!')

    def test_muestra_la_entrada_del_personal(self):
        r = self.client.get(f'{self.url}?next={self.caja}')
        self.assertContains(r, 'Panel del personal')
        self.assertContains(r, 'csrfmiddlewaretoken')
        self.assertContains(r, f'name="next" value="{self.caja}"')
        self.assertNotContains(r, 'Django')

    def test_personal_entra_y_vuelve_al_next(self):
        r = self.client.post(f'{self.url}?next={self.caja}',
                             {'username': 'personal_login', 'password': 'Pruebas123!', 'next': self.caja})
        self.assertRedirects(r, self.caja)

    def test_clave_incorrecta_muestra_error(self):
        r = self.client.post(self.url, {'username': 'personal_login', 'password': 'otra'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'mensaje--error')

    def test_usuario_sin_permiso_lo_ve_explicado(self):
        self.client.force_login(self.cliente)
        r = self.client.get(f'{self.url}?next={self.caja}')
        self.assertContains(r, 'no tiene permiso')
