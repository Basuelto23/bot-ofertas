# CAZADOR DE OFERTAS: explora varias tiendas (Falabella, Paris, Ripley, Easy, DBS),
# encuentra productos con descuento, evita duplicados, y publica cada uno en
# el canal correcto (gratis o premium) según qué tan buena sea la oferta.
#
# MODOS DE EJECUCIÓN (se elige al correr el script):
#   python cazador_ofertas.py nube   -> solo Falabella y DBS (para GitHub Actions)
#   python cazador_ofertas.py local  -> solo Paris, Ripley y Easy (para tu PC)
#   python cazador_ofertas.py todas  -> las 5 tiendas (solo para pruebas)
# Si no le pasas nada, usa "todas".

import requests
import json
import os
import re
import time
import random
import unicodedata
from bs4 import BeautifulSoup

import sys
sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------
# MODO DE EJECUCIÓN
# ---------------------------------------------------------------------
# sys.argv es la lista de "palabras" con que se llamó al script.
# Ejemplo: "python cazador_ofertas.py local" -> sys.argv[1] es "local".
MODO = sys.argv[1].lower() if len(sys.argv) > 1 else "todas"

if MODO not in ("nube", "local", "todas"):
    print(f"⚠️ El modo '{MODO}' no existe. Opciones: nube, local, todas. Usaré 'todas'.", flush=True)
    MODO = "todas"

# ---------------------------------------------------------------------
# CREDENCIALES DE TELEGRAM
# ---------------------------------------------------------------------
# Intentamos usar config.py (para cuando corres el bot en tu compu).
# Si no existe (por ejemplo, cuando corre en GitHub Actions), buscamos
# la informacion en variables de entorno, que es donde GitHub guarda
# los "Secrets" de forma segura.
try:
    import config
    TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID_GRATIS = config.TELEGRAM_CHAT_ID_GRATIS
    TELEGRAM_CHAT_ID_PREMIUM = config.TELEGRAM_CHAT_ID_PREMIUM
    print("🔑 Usando credenciales de config.py (modo local)", flush=True)
except ImportError:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID_GRATIS = os.environ["TELEGRAM_CHAT_ID_GRATIS"]
    TELEGRAM_CHAT_ID_PREMIUM = os.environ["TELEGRAM_CHAT_ID_PREMIUM"]
    print("🔑 Usando credenciales de variables de entorno (modo GitHub Actions)", flush=True)

# ---------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------------------
URL_OFERTAS_FALABELLA = "https://www.falabella.com/falabella-cl/collection/ofertas"
URL_OFERTAS_PARIS = "https://www.paris.cl/mujer/ofertas/"
DOMINIO_PARIS = "https://www.paris.cl"

# Las 4 categorias de "outlet" de Ripley donde estan las ofertas
CATEGORIAS_RIPLEY = [
    "https://simple.ripley.cl/outlet/calzado",
    "https://simple.ripley.cl/outlet/decohogar",
    "https://simple.ripley.cl/outlet/electro",
    "https://simple.ripley.cl/outlet/moda",
]

# Las 18 categorias de Easy que confirmamos que son de ofertas reales
CLUSTERS_OFERTAS_EASY = [
    "https://www.easy.cl/cluster/7930",
    "https://www.easy.cl/cluster/7952",
    "https://www.easy.cl/cluster/8098",
    "https://www.easy.cl/cluster/8100",
    "https://www.easy.cl/cluster/3006",
    "https://www.easy.cl/cluster/6810",
    "https://www.easy.cl/cluster/3003",
    "https://www.easy.cl/cluster/6286",
    "https://www.easy.cl/cluster/5360",
    "https://www.easy.cl/cluster/7054",
    "https://www.easy.cl/cluster/4343",
    "https://www.easy.cl/cluster/8084",
    "https://www.easy.cl/cluster/5267",
    "https://www.easy.cl/cluster/6826",
    "https://www.easy.cl/cluster/4428",
    "https://www.easy.cl/cluster/1582",
    "https://www.easy.cl/cluster/7495",
    "https://www.easy.cl/cluster/5359",
]

# Las 4 paginas de ofertas de DBS (tienda de belleza y cosmetica)
PAGINAS_DBS = [
    "https://dbs.cl/sale",
    "https://dbs.cl/sale?p=2",
    "https://dbs.cl/sale?p=3",
    "https://dbs.cl/sale?p=4",
]

DESCUENTO_MINIMO_GRATIS = 30    # 30% a 49% -> canal gratis
DESCUENTO_MINIMO_PREMIUM = 50   # 50% o más -> canal premium

# Cada modo usa su propio "cuaderno de memoria" para no chocar:
# - nube: el de siempre, que vive en GitHub y el workflow actualiza solo
# - local (y todas): uno nuevo que se queda solo en tu PC
if MODO == "nube":
    ARCHIVO_HISTORIAL = "historial_ofertas.json"
else:
    ARCHIVO_HISTORIAL = "historial_local.json"

SEGUNDOS_ENTRE_MENSAJES = 2.5

# Headers "de navegador real" (Chrome en Windows).
CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "es-CL,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Cache-Control": "max-age=0",
}

# Pequeña espera aleatoria antes de empezar, para no ser tan predecibles.
segundos_espera = random.randint(5, 40)
print(f"⏳ Esperando {segundos_espera} segundos antes de empezar...", flush=True)
time.sleep(segundos_espera)
print("▶️ Empezando a buscar ofertas...", flush=True)


# ---------------------------------------------------------------------
# UTILIDADES COMPARTIDAS
# ---------------------------------------------------------------------
def reparar_texto(texto):
    """Corrige tildes/ñ mal codificadas, si hace falta."""
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return texto


def formatear_precio(numero):
    return f"{numero:,}".replace(",", ".")


def pedir_pagina(url):
    """
    Pide una página web con reintentos automáticos. Si falla por algo
    pasajero (se cortó la conexión, el sitio respondió con un error
    temporal), espera un poco y vuelve a intentar, hasta 3 veces.
    Si la tienda nos BLOQUEA (código 403) o la página no existe (404),
    no reintenta, porque insistir al tiro no cambia nada.
    Devuelve la respuesta, o None si nunca hubo respuesta.
    """
    ultima_respuesta = None
    for intento in range(1, 4):
        try:
            respuesta = requests.get(url, headers=CABECERAS, timeout=15)
            ultima_respuesta = respuesta
            if respuesta.status_code == 200:
                return respuesta
            if respuesta.status_code in (403, 404):
                return respuesta
            print(f"   ⚠️ Intento {intento}: respondió código {respuesta.status_code}, reintentando...", flush=True)
        except requests.RequestException as error:
            print(f"   ⚠️ Intento {intento}: problema de conexión ({error}), reintentando...", flush=True)
        time.sleep(5 * intento)  # espera 5s, luego 10s, luego 15s
    return ultima_respuesta


def extraer_bloque_next_data(html):
    """
    Busca el bloque <script id="__NEXT_DATA__"> dentro de un HTML,
    y devuelve el JSON ya interpretado. Lo usan Ripley y Easy, que
    comparten esta misma forma de guardar los datos de productos.
    Devuelve None si no lo encuentra.
    """
    inicio = html.find('<script id="__NEXT_DATA__"')
    if inicio == -1:
        return None
    inicio = html.find(">", inicio) + 1
    fin = html.find("</script>", inicio)
    bloque_json = html[inicio:fin]
    return json.loads(bloque_json)


def imprimir_diagnostico_bloqueo(respuesta):
    """
    Cuando una tienda nos rechaza, esto imprime las cabeceras que ELLOS
    nos mandaron de vuelta. Sirve para detectar pistas de que sistema
    de seguridad anti-bot estan usando (ej: 'cf-ray' es de Cloudflare,
    'x-akamai...' es de Akamai, etc.), asi sabemos contra que estamos
    peleando.
    """
    pistas_conocidas = ["cf-ray", "cf-mitigated", "server", "x-akamai-transformed",
                         "x-akamai-request-id", "x-px-block", "x-datadome", "via"]
    headers_relevantes = {
        clave: valor for clave, valor in respuesta.headers.items()
        if clave.lower() in pistas_conocidas
    }
    print(f"   🔬 Diagnóstico - Headers relevantes: {headers_relevantes}", flush=True)
    print(f"   🔬 Diagnóstico - Todos los headers: {dict(respuesta.headers)}", flush=True)


# ---------------------------------------------------------------------
# MEMORIA (HISTORIAL)
# ---------------------------------------------------------------------
def cargar_historial():
    if not os.path.exists(ARCHIVO_HISTORIAL):
        return {}
    with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def guardar_historial(historial):
    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as archivo:
        json.dump(historial, archivo, indent=4, ensure_ascii=False)


# ---------------------------------------------------------------------
# LECTOR: FALABELLA
# ---------------------------------------------------------------------
def extraer_precio_falabella(producto, tipo_buscado):
    for paquete_precio in producto.get("prices", []):
        if paquete_precio.get("type") == tipo_buscado:
            lista_valores = paquete_precio.get("price", [])
            if lista_valores:
                return int(lista_valores[0].replace(".", ""))
    return None


def buscar_ofertas_falabella():
    print("🔍 Buscando ofertas en Falabella...", flush=True)
    respuesta = pedir_pagina(URL_OFERTAS_FALABELLA)

    if respuesta is None:
        print("   ❌ No pude conectarme a Falabella después de varios intentos.", flush=True)
        return []

    respuesta.encoding = "utf-8"

    if respuesta.status_code != 200:
        print(f"   ❌ No pude acceder a Falabella. Código: {respuesta.status_code}", flush=True)
        return []

    sopa = BeautifulSoup(respuesta.text, "lxml")
    tag_datos = sopa.find("script", id="__NEXT_DATA__")

    if not tag_datos:
        print("   ❌ No encontré el bloque de datos de Falabella. La página pudo haber cambiado.", flush=True)
        return []

    datos = json.loads(tag_datos.string)
    resultados_crudos = datos.get("props", {}).get("pageProps", {}).get("results", [])

    productos_por_link = {}

    for producto in resultados_crudos:
        titulo = producto.get("displayName")
        if titulo:
            titulo = reparar_texto(titulo)

        link = producto.get("url")
        precio_oferta = extraer_precio_falabella(producto, "internetPrice")
        precio_normal = extraer_precio_falabella(producto, "normalPrice")

        if not titulo or not link or not precio_oferta or not precio_normal or precio_normal == 0:
            continue

        descuento = round((1 - (precio_oferta / precio_normal)) * 100)

        if link in productos_por_link:
            continue

        productos_por_link[link] = {
            "tienda": "Falabella",
            "titulo": titulo,
            "precio_oferta": precio_oferta,
            "precio_normal": precio_normal,
            "descuento": descuento,
            "link": link
        }

    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Falabella.", flush=True)
    return list(productos_por_link.values())


# ---------------------------------------------------------------------
# LECTOR: PARIS
# ---------------------------------------------------------------------
def limpiar_precio_paris(texto):
    texto = texto.replace("$", "").replace(".", "").strip()
    return int(texto) if texto.isdigit() else None


def buscar_ofertas_paris():
    print("🔍 Buscando ofertas en Paris...", flush=True)
    respuesta = pedir_pagina(URL_OFERTAS_PARIS)

    if respuesta is None:
        print("   ❌ No pude conectarme a Paris después de varios intentos.", flush=True)
        return []

    respuesta.encoding = "utf-8"

    if respuesta.status_code != 200:
        print(f"   ❌ No pude acceder a Paris. Código: {respuesta.status_code}", flush=True)
        imprimir_diagnostico_bloqueo(respuesta)
        return []

    sopa = BeautifulSoup(respuesta.text, "lxml")
    tarjetas = sopa.find_all("a", id=lambda v: v and v.startswith("product-"))

    productos_por_link = {}

    for tarjeta in tarjetas:
        link = tarjeta.get("href")
        if not link:
            continue
        if link.startswith("/"):
            link = DOMINIO_PARIS + link

        spans_titulo = tarjeta.find_all(
            lambda tag: tag.name == "span" and tag.get("class") and
            any("line-clamp" in c for c in tag.get("class"))
        )
        if len(spans_titulo) < 2:
            continue
        marca = reparar_texto(spans_titulo[0].get_text(strip=True))
        nombre = reparar_texto(spans_titulo[1].get_text(strip=True))
        titulo = f"{marca} {nombre}"

        precio_oferta = None
        precio_normal = None
        bloques_precio = tarjeta.find_all(attrs={"data-testid": "paris-pod-price"})
        for bloque in bloques_precio:
            span_precio = bloque.find("span")
            if not span_precio:
                continue
            clases = span_precio.get("class", [])
            valor = limpiar_precio_paris(span_precio.get_text(strip=True))
            if valor is None:
                continue
            if any("line-through" in c for c in clases):
                precio_normal = valor
            else:
                precio_oferta = valor

        if not titulo or not link or not precio_oferta or not precio_normal or precio_normal == 0:
            continue

        etiqueta_descuento = tarjeta.find(attrs={"data-testid": "paris-label"})
        if etiqueta_descuento and etiqueta_descuento.get("aria-label", "").endswith("%"):
            descuento = int(etiqueta_descuento["aria-label"].replace("%", ""))
        else:
            descuento = round((1 - (precio_oferta / precio_normal)) * 100)

        if link in productos_por_link:
            continue

        productos_por_link[link] = {
            "tienda": "Paris",
            "titulo": titulo,
            "precio_oferta": precio_oferta,
            "precio_normal": precio_normal,
            "descuento": descuento,
            "link": link
        }

    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Paris.", flush=True)
    return list(productos_por_link.values())


# ---------------------------------------------------------------------
# LECTOR: RIPLEY
# ---------------------------------------------------------------------
def armar_slug_ripley(texto):
    """
    Convierte un nombre de producto en el formato que usa Ripley
    para armar sus links (minusculas, sin tildes, con guiones).
    """
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[^a-z0-9\s-]", "", texto)
    texto = re.sub(r"\s+", "-", texto).strip("-")
    return texto


def buscar_ofertas_ripley():
    print("🔍 Buscando ofertas en Ripley...", flush=True)
    productos_por_link = {}
    ya_se_imprimio_diagnostico = False

    for categoria in CATEGORIAS_RIPLEY:
        try:
            respuesta = pedir_pagina(categoria)

            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {categoria} después de varios intentos.", flush=True)
                continue

            if respuesta.status_code != 200:
                print(f"   ⚠️ No pude acceder a {categoria}. Código: {respuesta.status_code}", flush=True)
                if not ya_se_imprimio_diagnostico:
                    imprimir_diagnostico_bloqueo(respuesta)
                    ya_se_imprimio_diagnostico = True
                continue

            datos = extraer_bloque_next_data(respuesta.text)
            if not datos:
                print(f"   ⚠️ No encontré datos en {categoria}", flush=True)
                continue

            productos_crudos = (
                datos.get("props", {})
                .get("pageProps", {})
                .get("findabilityProps", {})
                .get("data", {})
                .get("products", [])
            )

            for producto in productos_crudos:
                titulo = producto.get("name")
                parent_id = producto.get("parentProductID")
                precio_oferta = producto.get("priceNumber")
                descuento = producto.get("discount")
                precio_normal_texto = producto.get("oldPrice")

                if not titulo or not parent_id or not precio_oferta or descuento is None:
                    continue

                titulo = reparar_texto(titulo)
                slug = armar_slug_ripley(titulo)
                link = f"https://simple.ripley.cl/{slug}-{parent_id.lower()}"

                precio_normal = None
                if precio_normal_texto:
                    texto_limpio = precio_normal_texto.replace("$", "").replace(".", "").strip()
                    if texto_limpio.isdigit():
                        precio_normal = int(texto_limpio)

                if link in productos_por_link:
                    continue

                productos_por_link[link] = {
                    "tienda": "Ripley",
                    "titulo": titulo,
                    "precio_oferta": precio_oferta,
                    "precio_normal": precio_normal if precio_normal else precio_oferta,
                    "descuento": descuento,
                    "link": link
                }

        except Exception as error:
            print(f"   ⚠️ Error en {categoria}: {error}", flush=True)

        time.sleep(random.uniform(2, 4))

    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Ripley.", flush=True)
    return list(productos_por_link.values())


# ---------------------------------------------------------------------
# LECTOR: EASY
# ---------------------------------------------------------------------
def buscar_ofertas_easy():
    print("🔍 Buscando ofertas en Easy...", flush=True)
    productos_por_link = {}
    ya_se_imprimio_diagnostico = False

    for categoria in CLUSTERS_OFERTAS_EASY:
        try:
            respuesta = pedir_pagina(categoria)

            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {categoria} después de varios intentos.", flush=True)
                continue

            if respuesta.status_code != 200:
                print(f"   ⚠️ No pude acceder a {categoria}. Código: {respuesta.status_code}", flush=True)
                if not ya_se_imprimio_diagnostico:
                    imprimir_diagnostico_bloqueo(respuesta)
                    ya_se_imprimio_diagnostico = True
                continue

            datos = extraer_bloque_next_data(respuesta.text)
            if not datos:
                print(f"   ⚠️ No encontré datos en {categoria}", flush=True)
                continue

            productos_crudos = (
                datos.get("props", {})
                .get("pageProps", {})
                .get("serverProductsResponse", {})
                .get("productList", [])
            )

            for producto in productos_crudos:
                titulo = producto.get("productName")
                link_texto = producto.get("linkText")
                precios = producto.get("prices", {})
                precio_normal = precios.get("normalPrice")
                precio_oferta = precios.get("offerPrice")

                if not titulo or not link_texto or not precio_normal or not precio_oferta:
                    continue
                if precio_oferta >= precio_normal:
                    continue

                titulo = reparar_texto(titulo)
                link = f"https://www.easy.cl/{link_texto}"

                descuento = round((1 - (precio_oferta / precio_normal)) * 100)

                if link in productos_por_link:
                    continue

                productos_por_link[link] = {
                    "tienda": "Easy",
                    "titulo": titulo,
                    "precio_oferta": precio_oferta,
                    "precio_normal": precio_normal,
                    "descuento": descuento,
                    "link": link
                }

        except Exception as error:
            print(f"   ⚠️ Error en {categoria}: {error}", flush=True)

        time.sleep(random.uniform(2, 4))

    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Easy.", flush=True)
    return list(productos_por_link.values())


# ---------------------------------------------------------------------
# LECTOR: DBS
# ---------------------------------------------------------------------
def procesar_tarjeta_dbs(tarjeta):
    titulo_h3 = tarjeta.find("h3", class_=lambda c: c and "product-item-name" in c)
    if not titulo_h3:
        return None

    enlace_nombre = titulo_h3.find("a")
    if not enlace_nombre:
        return None

    titulo = reparar_texto(enlace_nombre.get_text(strip=True))
    link = enlace_nombre.get("href")

    precio_oferta_tag = tarjeta.find("span", id=lambda v: v and v.startswith("product-price-"))
    precio_normal_tag = tarjeta.find("span", id=lambda v: v and v.startswith("old-price-"))

    if not precio_oferta_tag or not precio_normal_tag:
        return None

    precio_oferta = precio_oferta_tag.get("data-price-amount")
    precio_normal = precio_normal_tag.get("data-price-amount")

    if not precio_oferta or not precio_normal:
        return None

    precio_oferta = int(float(precio_oferta))
    precio_normal = int(float(precio_normal))

    if not titulo or not link or precio_oferta >= precio_normal or precio_normal == 0:
        return None

    descuento = round((1 - (precio_oferta / precio_normal)) * 100)

    return {
        "tienda": "DBS",
        "titulo": titulo,
        "precio_oferta": precio_oferta,
        "precio_normal": precio_normal,
        "descuento": descuento,
        "link": link
    }


def buscar_ofertas_dbs():
    print("🔍 Buscando ofertas en DBS...", flush=True)
    productos_por_link = {}

    for url_pagina in PAGINAS_DBS:
        try:
            respuesta = pedir_pagina(url_pagina)

            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {url_pagina} después de varios intentos.", flush=True)
                continue

            if respuesta.status_code != 200:
                print(f"   ⚠️ No pude acceder a {url_pagina}. Código: {respuesta.status_code}", flush=True)
                continue

            sopa = BeautifulSoup(respuesta.text, "lxml")
            tarjetas = sopa.find_all("li", class_=lambda c: c and "product-item" in c)

            for tarjeta in tarjetas:
                producto = procesar_tarjeta_dbs(tarjeta)
                if producto:
                    link = producto["link"]
                    productos_por_link[link] = producto

        except Exception as error:
            print(f"   ⚠️ Error en {url_pagina}: {error}", flush=True)

        time.sleep(random.uniform(2, 4))

    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en DBS.", flush=True)
    return list(productos_por_link.values())


# ---------------------------------------------------------------------
# ENVÍO A TELEGRAM
# ---------------------------------------------------------------------
def enviar_alerta_telegram(datos, chat_id, es_premium):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    etiqueta = "💎 <b>OFERTA PREMIUM</b> 💎" if es_premium else "🔥 <b>¡OFERTA!</b> 🔥"

    mensaje = (
        f"{etiqueta}\n\n"
        f"🏬 <i>{datos['tienda']}</i>\n"
        f"📦 <b>{datos['titulo']}</b>\n\n"
        f"💰 Precio oferta: <b>${formatear_precio(datos['precio_oferta'])}</b>\n"
        f"🏷️ Precio normal: <s>${formatear_precio(datos['precio_normal'])}</s>\n"
        f"📉 Descuento: <b>{datos['descuento']}%</b>\n\n"
        f"🔗 <a href=\"{datos['link']}\">Ver producto</a>"
    )

    datos_envio = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    respuesta = requests.post(url, data=datos_envio)

    if respuesta.status_code == 200:
        print(f"   ✅ Enviado a canal {'PREMIUM' if es_premium else 'GRATIS'}", flush=True)
    else:
        print(f"   ❌ Falló el envío. Código: {respuesta.status_code} - {respuesta.text}", flush=True)


# ---------------------------------------------------------------------
# LÓGICA PRINCIPAL
# ---------------------------------------------------------------------
def procesar_producto(producto, historial):
    descuento = producto["descuento"]
    link = producto["link"]

    if descuento < DESCUENTO_MINIMO_GRATIS:
        return historial

    es_premium = descuento >= DESCUENTO_MINIMO_PREMIUM
    chat_id = TELEGRAM_CHAT_ID_PREMIUM if es_premium else TELEGRAM_CHAT_ID_GRATIS

    registro_anterior = historial.get(link)

    if registro_anterior is None:
        print(f"🆕 Nuevo [{producto['tienda']}]: {producto['titulo']} ({descuento}%)", flush=True)
        enviar_alerta_telegram(producto, chat_id, es_premium)
        historial[link] = {"precio_oferta": producto["precio_oferta"], "canal": "premium" if es_premium else "gratis"}
        time.sleep(SEGUNDOS_ENTRE_MENSAJES)

    elif producto["precio_oferta"] < registro_anterior["precio_oferta"]:
        print(f"📉 Bajó más [{producto['tienda']}]: {producto['titulo']} ({descuento}%)", flush=True)
        enviar_alerta_telegram(producto, chat_id, es_premium)
        historial[link] = {"precio_oferta": producto["precio_oferta"], "canal": "premium" if es_premium else "gratis"}
        time.sleep(SEGUNDOS_ENTRE_MENSAJES)

    return historial


if __name__ == "__main__":
    print("=" * 50, flush=True)
    print(f"🤖 Modo de ejecución: {MODO.upper()}", flush=True)
    print(f"🗂️ Cuaderno de memoria: {ARCHIVO_HISTORIAL}", flush=True)

    todos_los_productos = []

    # Tiendas que funcionan desde GitHub Actions (la nube)
    if MODO in ("nube", "todas"):
        todos_los_productos += buscar_ofertas_falabella()
        time.sleep(3)
        todos_los_productos += buscar_ofertas_dbs()
        time.sleep(3)

    # Tiendas que solo funcionan desde tu casa (IP residencial)
    if MODO in ("local", "todas"):
        todos_los_productos += buscar_ofertas_paris()
        time.sleep(3)
        todos_los_productos += buscar_ofertas_ripley()
        time.sleep(3)
        todos_los_productos += buscar_ofertas_easy()

    print(f"\n📦 Total combinado: {len(todos_los_productos)} producto(s).\n", flush=True)

    historial = cargar_historial()

    enviados = 0
    for producto in todos_los_productos:
        antes = len(historial)
        historial = procesar_producto(producto, historial)
        if len(historial) > antes:
            enviados += 1
            guardar_historial(historial)

    print(f"\n✅ Listo. Se enviaron {enviados} alerta(s) nueva(s). Historial actualizado.", flush=True)
