"""Compila locale/<idioma>/LC_MESSAGES/django.po a django.mo sin herramientas externas.

Django usa msgfmt (GNU gettext) en compilemessages, que no viene en Windows. Este comando hace lo
mismo en Python puro para el formato que usa Kippu: msgid, msgid_plural, msgstr y msgstr[n].
Las entradas "fuzzy" o sin traducir no se incluyen, como hace msgfmt.

Uso: python manage.py compilar_traducciones
"""
import ast
import struct
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def leer_po(texto):
    """Devuelve [(msgid, msgid_plural, [msgstr...], fuzzy)] incluida la cabecera (msgid vacío)."""
    entradas, actual, campo, fuzzy = [], None, None, False

    def cerrar():
        if actual is not None:
            entradas.append((actual["msgid"], actual.get("msgid_plural"), actual["msgstr"], actual["fuzzy"]))

    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if linea.startswith("#"):
            if linea.startswith("#,") and "fuzzy" in linea:
                fuzzy = True
            continue
        if linea.startswith("msgid "):
            cerrar()
            actual = {"msgid": "", "msgstr": [], "fuzzy": fuzzy}
            fuzzy = False
            campo = ("msgid",)
            valor = linea[len("msgid "):]
        elif linea.startswith("msgid_plural "):
            actual["msgid_plural"] = ""
            campo = ("msgid_plural",)
            valor = linea[len("msgid_plural "):]
        elif linea.startswith("msgstr["):
            indice = int(linea[len("msgstr["):linea.index("]")])
            while len(actual["msgstr"]) <= indice:
                actual["msgstr"].append("")
            campo = ("msgstr", indice)
            valor = linea[linea.index("]") + 1:].strip()
        elif linea.startswith("msgstr "):
            actual["msgstr"] = [""]
            campo = ("msgstr", 0)
            valor = linea[len("msgstr "):]
        elif linea.startswith('"'):
            valor = linea
        else:
            raise ValueError(f"Línea no reconocida en el .po: {linea}")
        texto_valor = ast.literal_eval(valor)
        if campo[0] == "msgstr":
            actual["msgstr"][campo[1]] += texto_valor
        else:
            actual[campo[0]] += texto_valor
    cerrar()
    return entradas


def escribir_mo(entradas):
    catalogo = {}
    for msgid, plural, msgstr, fuzzy in entradas:
        if msgid and (fuzzy or not all(msgstr)):
            continue  # sin traducir o dudosa: gettext devuelve el español
        clave = msgid if plural is None else f"{msgid}\x00{plural}"
        catalogo[clave] = "\x00".join(msgstr)
    claves = sorted(catalogo)
    ids = [clave.encode("utf-8") for clave in claves]
    strs = [catalogo[clave].encode("utf-8") for clave in claves]
    inicio_ids = 7 * 4 + 16 * len(claves)
    tabla_ids, tabla_strs, datos_ids, datos_strs = [], [], b"", b""
    for valor in ids:
        tabla_ids.append((len(valor), inicio_ids + len(datos_ids)))
        datos_ids += valor + b"\x00"
    inicio_strs = inicio_ids + len(datos_ids)
    for valor in strs:
        tabla_strs.append((len(valor), inicio_strs + len(datos_strs)))
        datos_strs += valor + b"\x00"
    cabecera = struct.pack("<7I", 0x950412DE, 0, len(claves), 7 * 4, 7 * 4 + 8 * len(claves), 0, 0)
    cuerpo = b"".join(struct.pack("<2I", *par) for par in tabla_ids + tabla_strs)
    return cabecera + cuerpo + datos_ids + datos_strs


def compilar(po):
    return escribir_mo(leer_po(Path(po).read_text(encoding="utf-8")))


class Command(BaseCommand):
    help = "Compila los .po de LOCALE_PATHS a .mo (sin msgfmt)."

    def handle(self, *args, **opciones):
        for carpeta in settings.LOCALE_PATHS:
            for po in sorted(Path(carpeta).glob("*/LC_MESSAGES/*.po")):
                mo = po.with_suffix(".mo")
                mo.write_bytes(compilar(po))
                self.stdout.write(f"{po} → {mo.name}")
