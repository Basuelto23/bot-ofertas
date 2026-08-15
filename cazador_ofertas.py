# CAZADOR DE OFERTAS: explora varias tiendas (Falabella, DBS, Paris, Easy, Lider),
# encuentra productos con descuento, evita duplicados, y publica cada uno en
# el canal correcto (gratis o premium) según qué tan buena sea la oferta.
# Los descuentos gigantes (75%+) se marcan como POSIBLE ERROR DE PRECIO.
# Los productos que calcen con lista_deseos.txt se marcan con 🎯 y se
# avisan desde un descuento más bajo (15%).
#
# MODOS DE EJECUCIÓN:
#   python cazador_ofertas.py local  -> UNA pasada por todas las tiendas y termina
#   python cazador_ofertas.py bucle  -> pasadas INFINITAS cada 30 min (CTRL+C para parar)
#   python cazador_ofertas.py nube   -> nada por ahora
#   python cazador_ofertas.py todas  -> igual que local
#
# NOTAS DE ESTADO:
# - Falabella: se leen PÁGINAS DE CATEGORÍA (su antigua colección de ofertas
#   quedó vacía tras un rediseño). Para agregar categorías: navega en
#   falabella.com a la categoría (la URL contiene "/category/") y pégala
#   en CATEGORIAS_FALABELLA. ¡No sirven URLs de "/product/"!
# - Ripley: PAUSADO. Su página dejó de incluir el bloque de datos legible.
# - Lider: lee "Liquidación Lider" (no-perecibles). Ahora recorre varias
#   subcategorías Y varias páginas por subcategoría (antes solo leía la
#   primera página de una sola subcategoría, así que se perdía la mayoría
#   de los productos en liquidación).
import requests
import json
import os
import re
import time
import random
import unicodedata
import subprocess
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding="utf-8")
# ---------------------------------------------------------------------
# MODO DE EJECUCIÓN
# ---------------------------------------------------------------------
MODO = sys.argv[1].lower() if len(sys.argv) > 1 else "todas"
if MODO not in ("nube", "local", "todas", "bucle"):
    print(f"⚠️ El modo '{MODO}' no existe. Opciones: nube, local, todas, bucle. Usaré 'todas'.", flush=True)
    MODO = "todas"
MINUTOS_ENTRE_PASADAS = 30  # espera del modo bucle entre pasada y pasada
# ---------------------------------------------------------------------
# CREDENCIALES DE TELEGRAM
# ---------------------------------------------------------------------
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
# Categorías de Falabella a vigilar (URLs con "/category/").
CATEGORIAS_FALABELLA = [
    "https://www.falabella.com/falabella-cl/category/cat2018/Celulares-y-Telefonos",
    "https://www.falabella.com/falabella-cl/category/cat4830/Zapatillas",
    "https://www.falabella.com/falabella-cl/category/cat2005/Computacion",
    "https://www.falabella.com/falabella-cl/category/cat3205/Perfumes",
    "https://www.falabella.com/falabella-cl/category/cat3145/Camas",
    "https://www.falabella.com/falabella-cl/category/cat2032/Audio",
]
MAX_PAGINAS_FALABELLA = 3
URL_OFERTAS_PARIS = "https://www.paris.cl/mujer/ofertas/"
DOMINIO_PARIS = "https://www.paris.cl"
# Las categorias "outlet" de Ripley (PAUSADO)
CATEGORIAS_RIPLEY = [
    "https://simple.ripley.cl/outlet/calzado",
    "https://simple.ripley.cl/outlet/decohogar",
    "https://simple.ripley.cl/outlet/electro",
    "https://simple.ripley.cl/outlet/moda",
]
# Categorias de Easy con ofertas reales
CLUSTERS_OFERTAS_EASY = [
    "https://www.easy.cl/cluster/7930",
    "https://www.easy.cl/cluster/7952",
    "https://www.easy.cl/cluster/8098",
    "https://www.easy.cl/cluster/8100",
    "https://www.easy.cl/cluster/3006",
    "https://www.easy.cl/cluster/3003",
    "https://www.easy.cl/cluster/5360",
    "https://www.easy.cl/cluster/7054",
    "https://www.easy.cl/cluster/8084",
    "https://www.easy.cl/cluster/5267",
    "https://www.easy.cl/cluster/6826",
    "https://www.easy.cl/cluster/4428",
    "https://www.easy.cl/cluster/1582",
    "https://www.easy.cl/cluster/5359",
]
# Las 4 paginas de ofertas de DBS
PAGINAS_DBS = [
    "https://dbs.cl/sale",
    "https://dbs.cl/sale?p=2",
    "https://dbs.cl/sale?p=3",
    "https://dbs.cl/sale?p=4",
]
# Categorias de "Liquidación Lider" (SOLO no-perecibles).
# Para agregar más: lider.cl -> Liquidación Lider -> elige categoría ->
# copia la URL (debe partir con lider.cl/browse/liquidacion-lider/) y
# pégala aquí. Las 4 de abajo ya están verificadas (misma estructura que
# la que ya usabas). Si Lider agrega/cambia subcategorías, revisa el menú
# de https://www.lider.cl/content/liquidacion-lider/95467052
CATEGORIAS_LIDER = [
    "https://www.lider.cl/browse/liquidacion-lider/electro/95467052_73455141",
    "https://www.lider.cl/browse/liquidacion-lider/electro/electrohogar/95467052_73455141_77393875",
    "https://www.lider.cl/browse/liquidacion-lider/electro/linea-blanca/95467052_73455141_43302143",
    "https://www.lider.cl/browse/liquidacion-lider/muebles/95467052_15955368",
]
MAX_PAGINAS_LIDER = 3
DOMINIO_LIDER = "https://www.lider.cl"
DESCUENTO_MINIMO_GRATIS = 30      # 30% a 49% -> canal gratis
DESCUENTO_MINIMO_PREMIUM = 50     # 50% a 74% -> canal premium
DESCUENTO_POSIBLE_ERROR = 75      # 75% o más -> premium con alerta de POSIBLE ERROR
DESCUENTO_MINIMO_DESEOS = 15      # productos de la lista de deseos avisan desde este %
ARCHIVO_LISTA_DESEOS = "lista_deseos.txt"
# Cada modo usa su propio "cuaderno de memoria"
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
def normalizar(texto):
    """Minúsculas y sin tildes, para comparar sin dramas."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    return texto.encode("ascii", "ignore").decode("utf-8")
def precio_texto_a_numero(texto):
    """Convierte un precio escrito ("$59.990") en número (59990)."""
    if not texto:
        return None
    limpio = str(texto).replace("$", "").replace(".", "").replace(" ", "").strip()
    return int(limpio) if limpio.isdigit() else None
def cargar_lista_deseos():
    """
    Lee lista_deseos.txt (una palabra o frase por línea; # = comentario).
    Devuelve la lista normalizada. Si el archivo no existe, lista vacía.
    """
    if not os.path.exists(ARCHIVO_LISTA_DESEOS):
        return []
    deseos = []
    with open(ARCHIVO_LISTA_DESEOS, "r", encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                deseos.append(normalizar(linea))
    return deseos
def buscar_deseo(titulo, lista_deseos):
    """Devuelve la palabra de la lista que aparece en el título, o None."""
    titulo_normalizado = normalizar(titulo)
    for palabra in lista_deseos:
        if palabra in titulo_normalizado:
            return palabra
    return None
def pedir_pagina(url):
    """
    Pide una página web con reintentos automáticos (hasta 3).
    Con 403 o 404 no reintenta. Devuelve la respuesta o None.
    """
    ultima_respuesta = None
    for intento in range(1, 4):
        try:
            respuesta = requests.get(url, headers=CABECERAS, timeout=20)
            ultima_respuesta = respuesta
            if respuesta.status_code == 200:
                return respuesta
            if respuesta.status_code in (403, 404):
                return respuesta
            print(f"   ⚠️ Intento {intento}: respondió código {respuesta.status_code}, reintentando...", flush=True)
        except requests.RequestException as error:
            print(f"   ⚠️ Intento {intento}: problema de conexión ({error}), reintentando...", flush=True)
        time.sleep(5 * intento)
    return ultima_respuesta
def extraer_bloque_next_data(html):
    """
    Busca el bloque <script id="__NEXT_DATA__"> (búsqueda flexible) y
    devuelve el JSON interpretado, o None si no está o está corrupto.
    """
    coincidencia = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.S,
    )
    if not coincidencia:
        return None
    try:
        return json.loads(coincidencia.group(1))
    except json.JSONDecodeError as error:
        print(f"   ⚠️ Encontré el bloque de datos pero no pude leerlo (JSON roto): {error}", flush=True)
        return None
def imprimir_pistas_pagina(html):
    """Pistas cuando una página respondió OK pero sin datos legibles."""
    print(f"   🔬 Pistas: la página mide {len(html)} caracteres.", flush=True)
    print(f"   🔬 Pistas: ¿contiene __NEXT_DATA__? -> {'__NEXT_DATA__' in html}", flush=True)
def imprimir_diagnostico_bloqueo(respuesta):
    """Pistas del sistema anti-bot cuando una tienda nos rechaza."""
    pistas_conocidas = ["cf-ray", "cf-mitigated", "server", "x-akamai-transformed",
                         "x-akamai-request-id", "x-px-block", "x-datadome", "via"]
    headers_relevantes = {
        clave: valor for clave, valor in respuesta.headers.items()
        if clave.lower() in pistas_conocidas
    }
    print(f"   🔬 Diagnóstico - Headers relevantes: {headers_relevantes}", flush=True)
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
# LECTOR: FALABELLA (por categorías, con paginación)
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
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for categoria in CATEGORIAS_FALABELLA:
        nombre_corto = categoria.rstrip("/").split("/")[-1]
        for numero_pagina in range(1, MAX_PAGINAS_FALABELLA + 1):
            if numero_pagina == 1:
                url = categoria
            else:
                separador = "&" if "?" in categoria else "?"
                url = f"{categoria}{separador}page={numero_pagina}"
            respuesta = pedir_pagina(url)
            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {nombre_corto} pág. {numero_pagina}.", flush=True)
                break
            respuesta.encoding = "utf-8"
            if respuesta.status_code != 200:
                print(f"   ⚠️ {nombre_corto} pág. {numero_pagina} respondió código {respuesta.status_code}.", flush=True)
                break
            datos = extraer_bloque_next_data(respuesta.text)
            if not datos:
                print(f"   ⚠️ Sin bloque de datos en {nombre_corto} pág. {numero_pagina}.", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_pistas_pagina(respuesta.text)
                    ya_se_imprimieron_pistas = True
                break
            resultados_crudos = datos.get("props", {}).get("pageProps", {}).get("results", [])
            if not isinstance(resultados_crudos, list):
                resultados_crudos = []
            nuevos_en_esta_pagina = 0
            for producto in resultados_crudos:
                titulo = producto.get("displayName")
                if titulo:
                    titulo = reparar_texto(titulo)
                link = producto.get("url")
                precio_oferta = extraer_precio_falabella(producto, "internetPrice")
                precio_normal = extraer_precio_falabella(producto, "normalPrice")
                if not titulo or not link or not precio_oferta or not precio_normal or precio_normal == 0:
                    continue
                if precio_oferta >= precio_normal:
                    continue
                if link in productos_por_link:
                    continue
                descuento = round((1 - (precio_oferta / precio_normal)) * 100)
                productos_por_link[link] = {
                    "tienda": "Falabella",
                    "titulo": titulo,
                    "precio_oferta": precio_oferta,
                    "precio_normal": precio_normal,
                    "descuento": descuento,
                    "link": link
                }
                nuevos_en_esta_pagina += 1
            print(f"   📄 {nombre_corto} pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) con descuento.", flush=True)
            if len(resultados_crudos) == 0:
                break
            time.sleep(random.uniform(2, 4))
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
# LECTOR: LIDER (Liquidación Lider — estructura Walmart, con paginación)
# ---------------------------------------------------------------------
def buscar_ofertas_lider():
    print("🔍 Buscando ofertas en Lider...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for categoria in CATEGORIAS_LIDER:
        nombre_corto = categoria.rstrip("/").split("/")[-1]
        for numero_pagina in range(1, MAX_PAGINAS_LIDER + 1):
            if numero_pagina == 1:
                url = categoria
            else:
                separador = "&" if "?" in categoria else "?"
                url = f"{categoria}{separador}page={numero_pagina}"
            try:
                respuesta = pedir_pagina(url)
                if respuesta is None:
                    print(f"   ⚠️ No pude conectarme a {nombre_corto} pág. {numero_pagina} después de varios intentos.", flush=True)
                    break
                if respuesta.status_code != 200:
                    print(f"   ⚠️ No pude acceder a {nombre_corto} pág. {numero_pagina}. Código: {respuesta.status_code}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_diagnostico_bloqueo(respuesta)
                        ya_se_imprimieron_pistas = True
                    break
                datos = extraer_bloque_next_data(respuesta.text)
                if not datos:
                    print(f"   ⚠️ No encontré datos en {nombre_corto} pág. {numero_pagina}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_pistas_pagina(respuesta.text)
                        ya_se_imprimieron_pistas = True
                    break
                pilas = (
                    datos.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("searchResult", {})
                    .get("itemStacks", [])
                )
                if not pilas:
                    print(f"   ⚠️ El bloque de datos de {nombre_corto} pág. {numero_pagina} venía sin productos.", flush=True)
                    break
                nuevos_en_esta_pagina = 0
                total_items_pagina = 0
                for pila in pilas:
                    for producto in pila.get("items", []):
                        total_items_pagina += 1
                        titulo = producto.get("name")
                        url_relativa = producto.get("canonicalUrl")
                        info_precio = producto.get("priceInfo") or {}
                        precio_oferta = precio_texto_a_numero(info_precio.get("linePrice"))
                        precio_normal = precio_texto_a_numero(info_precio.get("wasPrice"))
                        if not titulo or not url_relativa or not precio_oferta or not precio_normal:
                            continue
                        if precio_oferta >= precio_normal:
                            continue
                        if producto.get("isOutOfStock"):
                            continue
                        titulo = reparar_texto(titulo)
                        link = DOMINIO_LIDER + url_relativa if url_relativa.startswith("/") else url_relativa
                        descuento = round((1 - (precio_oferta / precio_normal)) * 100)
                        if link in productos_por_link:
                            continue
                        productos_por_link[link] = {
                            "tienda": "Lider",
                            "titulo": titulo,
                            "precio_oferta": precio_oferta,
                            "precio_normal": precio_normal,
                            "descuento": descuento,
                            "link": link
                        }
                        nuevos_en_esta_pagina += 1
                print(f"   📄 {nombre_corto} pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) nuevo(s) con descuento ({total_items_pagina} en la página).", flush=True)
                if total_items_pagina == 0:
                    break
                if numero_pagina > 1 and nuevos_en_esta_pagina == 0:
                    # Probable señal de que "?page=" no cambió nada (misma página de siempre):
                    # no seguimos gastando pedidos en esta categoría.
                    break
            except Exception as error:
                print(f"   ⚠️ Error en {nombre_corto} pág. {numero_pagina}: {error}", flush=True)
                break
            time.sleep(random.uniform(2, 4))
    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Lider.", flush=True)
    return list(productos_por_link.values())
# ---------------------------------------------------------------------
# LECTOR: RIPLEY (PAUSADO - no se llama desde el programa principal)
# ---------------------------------------------------------------------
def armar_slug_ripley(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[^a-z0-9\s-]", "", texto)
    texto = re.sub(r"\s+", "-", texto).strip("-")
    return texto
def buscar_ofertas_ripley():
    print("🔍 Buscando ofertas en Ripley...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for categoria in CATEGORIAS_RIPLEY:
        try:
            respuesta = pedir_pagina(categoria)
            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {categoria} después de varios intentos.", flush=True)
                continue
            if respuesta.status_code != 200:
                print(f"   ⚠️ No pude acceder a {categoria}. Código: {respuesta.status_code}", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_diagnostico_bloqueo(respuesta)
                    ya_se_imprimieron_pistas = True
                continue
            datos = extraer_bloque_next_data(respuesta.text)
            if not datos:
                print(f"   ⚠️ No encontré datos en {categoria}", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_pistas_pagina(respuesta.text)
                    ya_se_imprimieron_pistas = True
                continue
            productos_crudos = (
                datos.get("props", {})
                .get("pageProps", {})
                .get("findabilityProps", {})
                .get("data", {})
                .get("products", [])
            )
            if not productos_crudos:
                print(f"   ⚠️ El bloque de datos de {categoria} venía sin productos.", flush=True)
                continue
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
                precio_normal = precio_texto_a_numero(precio_normal_texto)
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
    ya_se_imprimieron_pistas = False
    for categoria in CLUSTERS_OFERTAS_EASY:
        try:
            respuesta = pedir_pagina(categoria)
            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {categoria} después de varios intentos.", flush=True)
                continue
            if respuesta.status_code != 200:
                print(f"   ⚠️ No pude acceder a {categoria}. Código: {respuesta.status_code}", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_diagnostico_bloqueo(respuesta)
                    ya_se_imprimieron_pistas = True
                continue
            datos = extraer_bloque_next_data(respuesta.text)
            if not datos:
                print(f"   ⚠️ No encontré datos en {categoria}", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_pistas_pagina(respuesta.text)
                    ya_se_imprimieron_pistas = True
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
            if not tarjetas:
                print(f"   ⚠️ {url_pagina} respondió OK pero sin tarjetas de producto.", flush=True)
                imprimir_pistas_pagina(respuesta.text)
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
# ENVÍO A TELEGRAM (blindado contra cortes de conexión)
# ---------------------------------------------------------------------
def enviar_alerta_telegram(datos, chat_id, es_premium):
    """
    Envía la alerta a Telegram con hasta 3 reintentos. Devuelve True si
    se envió, False si no.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    es_posible_error = datos["descuento"] >= DESCUENTO_POSIBLE_ERROR
    if es_posible_error:
        etiqueta = "⚡🚨 <b>POSIBLE ERROR DE PRECIO</b> 🚨⚡"
        advertencia = "\n⚠️ <i>Descuento inusualmente alto. ¡Corre antes de que lo corrijan! La tienda podría anular la compra si confirma que fue un error.</i>\n"
    elif es_premium:
        etiqueta = "💎 <b>OFERTA PREMIUM</b> 💎"
        advertencia = ""
    else:
        etiqueta = "🔥 <b>¡OFERTA!</b> 🔥"
        advertencia = ""
    linea_deseo = ""
    if datos.get("deseo"):
        linea_deseo = f"🎯 <b>DE TU LISTA:</b> {datos['deseo']}\n"
    mensaje = (
        f"{etiqueta}\n"
        f"{linea_deseo}\n"
        f"🏬 <i>{datos['tienda']}</i>\n"
        f"📦 <b>{datos['titulo']}</b>\n\n"
        f"💰 Precio oferta: <b>${formatear_precio(datos['precio_oferta'])}</b>\n"
        f"🏷️ Precio normal: <s>${formatear_precio(datos['precio_normal'])}</s>\n"
        f"📉 Descuento: <b>{datos['descuento']}%</b>\n"
        f"{advertencia}\n"
        f"🔗 <a href=\"{datos['link']}\">Ver producto</a>"
    )
    datos_envio = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    for intento in range(1, 4):
        try:
            respuesta = requests.post(url, data=datos_envio, timeout=15)
            if respuesta.status_code == 200:
                tipo = "POSIBLE ERROR" if es_posible_error else ("PREMIUM" if es_premium else "GRATIS")
                print(f"   ✅ Enviado a canal ({tipo})", flush=True)
                return True
            if respuesta.status_code == 429:
                print(f"   ⏳ Telegram pide calma, esperando antes de reintentar...", flush=True)
                time.sleep(10 * intento)
                continue
            print(f"   ❌ Falló el envío. Código: {respuesta.status_code} - {respuesta.text}", flush=True)
            return False
        except requests.RequestException as error:
            print(f"   ⚠️ Intento {intento} de envío falló por conexión, reintentando...", flush=True)
            time.sleep(5 * intento)
    print(f"   ❌ No pude enviar esta oferta tras 3 intentos. Saldrá en la próxima pasada.", flush=True)
    return False
# ---------------------------------------------------------------------
# LÓGICA PRINCIPAL
# ---------------------------------------------------------------------
def procesar_producto(producto, historial, lista_deseos):
    descuento = producto["descuento"]
    link = producto["link"]
    deseo = buscar_deseo(producto["titulo"], lista_deseos) if lista_deseos else None
    producto["deseo"] = deseo
    umbral = DESCUENTO_MINIMO_DESEOS if deseo else DESCUENTO_MINIMO_GRATIS
    if descuento < umbral:
        return historial
    es_premium = descuento >= DESCUENTO_MINIMO_PREMIUM
    chat_id = TELEGRAM_CHAT_ID_PREMIUM if es_premium else TELEGRAM_CHAT_ID_GRATIS
    registro_anterior = historial.get(link)
    if registro_anterior is None:
        marca_deseo = " 🎯" if deseo else ""
        print(f"🆕 Nuevo{marca_deseo} [{producto['tienda']}]: {producto['titulo']} ({descuento}%)", flush=True)
        se_envio = enviar_alerta_telegram(producto, chat_id, es_premium)
        if se_envio:
            historial[link] = {"precio_oferta": producto["precio_oferta"], "canal": "premium" if es_premium else "gratis"}
        time.sleep(SEGUNDOS_ENTRE_MENSAJES)
    elif producto["precio_oferta"] < registro_anterior["precio_oferta"]:
        print(f"📉 Bajó más [{producto['tienda']}]: {producto['titulo']} ({descuento}%)", flush=True)
        se_envio = enviar_alerta_telegram(producto, chat_id, es_premium)
        if se_envio:
            historial[link] = {"precio_oferta": producto["precio_oferta"], "canal": "premium" if es_premium else "gratis"}
        time.sleep(SEGUNDOS_ENTRE_MENSAJES)
    return historial
def hacer_una_pasada():
    """Una pasada completa: busca en todas las tiendas activas y envía lo nuevo."""
    lista_deseos = cargar_lista_deseos()
    if lista_deseos:
        print(f"🎯 Lista de deseos activa ({len(lista_deseos)} palabra(s)).", flush=True)
    else:
        print("🎯 Sin lista de deseos (crea lista_deseos.txt si quieres usarla).", flush=True)
    todos_los_productos = []
    todos_los_productos += buscar_ofertas_falabella()
    time.sleep(3)
    todos_los_productos += buscar_ofertas_dbs()
    time.sleep(3)
    todos_los_productos += buscar_ofertas_paris()
    time.sleep(3)
    todos_los_productos += buscar_ofertas_easy()
    time.sleep(3)
    todos_los_productos += buscar_ofertas_lider()
    print(f"\n📦 Total combinado: {len(todos_los_productos)} producto(s).\n", flush=True)
    historial = cargar_historial()
    enviados = 0
    for producto in todos_los_productos:
        antes = len(historial)
        historial = procesar_producto(producto, historial, lista_deseos)
        if len(historial) > antes:
            enviados += 1
            guardar_historial(historial)
    print(f"\n✅ Pasada lista. Se enviaron {enviados} alerta(s) nueva(s).", flush=True)
def activar_candado_energia():
    """En Termux, evita que Android duerma el proceso con la pantalla apagada."""
    try:
        subprocess.run(["termux-wake-lock"], timeout=5)
        print("🔒 Candado de energía activado (termux-wake-lock).", flush=True)
    except Exception:
        pass
if __name__ == "__main__":
    print("=" * 50, flush=True)
    print(f"🤖 Modo de ejecución: {MODO.upper()}", flush=True)
    print(f"🗂️ Cuaderno de memoria: {ARCHIVO_HISTORIAL}", flush=True)
    if MODO == "nube":
        print("ℹ️ El modo nube no tiene tiendas asignadas actualmente.", flush=True)
    elif MODO == "bucle":
        activar_candado_energia()
        print(f"🔁 Bucle iniciado: una pasada cada {MINUTOS_ENTRE_PASADAS} minutos. CTRL+C para detener.", flush=True)
        numero_pasada = 0
        try:
            while True:
                numero_pasada += 1
                print("\n" + "=" * 50, flush=True)
                print(f"🕐 {time.strftime('%H:%M:%S')} — Pasada #{numero_pasada}", flush=True)
                try:
                    hacer_una_pasada()
                except Exception as error:
                    print(f"💥 La pasada #{numero_pasada} falló ({error}). El bucle sigue vivo.", flush=True)
                print(f"😴 {time.strftime('%H:%M:%S')} — Durmiendo {MINUTOS_ENTRE_PASADAS} minutos...", flush=True)
                time.sleep(MINUTOS_ENTRE_PASADAS * 60)
        except KeyboardInterrupt:
            print("\n🛑 Bucle detenido a mano. ¡Hasta la próxima!", flush=True)
    else:
        segundos_espera = random.randint(5, 40)
        print(f"⏳ Esperando {segundos_espera} segundos antes de empezar...", flush=True)
        time.sleep(segundos_espera)
        hacer_una_pasada()
        print("Historial actualizado.", flush=True)
