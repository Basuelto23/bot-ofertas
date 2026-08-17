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
# - Paris: ahora recorre 3 secciones de ofertas (mujer/hombre/tecnología)
#   con paginación, en vez de solo "mujer" y una sola página.
# - Easy: ahora pagina cada cluster en vez de leer solo la primera página.
# - MercadoLibre: la URL correcta es mercadolibre.cl/ofertas (NO
#   listado.mercadolibre.cl/ofertas, esa devuelve una página vacía). Ya
#   verificado con un navegador real: usa tarjetas "poly-card" con
#   "poly-component__title" y "andes-money-amount__fraction" para los
#   precios, que es justo lo que el código busca. Pagina con "?page=2".
# - Jumbo: SÍ se puede leer liviano (con solo "requests"), pero no de la
#   forma obvia. jumbo-ofertas no trae los productos en un bloque JSON
#   limpio tipo Falabella: los datos vienen repartidos en varios
#   <script>self.__next_f.push([...])</script> (formato interno de
#   Next.js) con el JSON escapado adentro de un string. El nombre y el
#   link de cada producto SÍ vienen limpios en un <script type="application/ld+json">
#   aparte. El bot junta ambas fuentes: saca precio/precio-lista de los
#   chunks de next_f y el link del bloque ld+json, cruzando por nombre.
#   Verificado en vivo: de 40 productos en una página, encontró 34 con
#   descuento y pudo linkear 31. Trae TODO (sin filtrar perecibles, tal
#   como se pidió), pero ¡ojo! cada página de Jumbo pesa ~4-4.5 MB — con
#   97 páginas en total, no conviene recorrerlas todas cada pasada (sería
#   varios cientos de MB de datos móviles). MAX_PAGINAS_JUMBO controla
#   cuántas se revisan; súbelo si tienes WiFi ilimitado y quieres más
#   cobertura, bájalo si te preocupan los datos móviles.
# - AliExpress: NO agregado todavía. Tiene protección anti-bot fuerte
#   (Cloudflare) y normalmente exige un navegador real, no pedidos HTTP
#   simples. No es viable corriéndolo liviano en Termux; si se agrega,
#   debería ser aparte (ej: en la nube con Playwright), no en el bucle
#   del celular.
# - ARREGLO "manda las mismas ofertas" (repetidas): se encontraron y
#   arreglaron 3 causas, todas verificadas con tests:
#   1) MercadoLibre: cada tarjeta trae en su URL parámetros de tracking
#      (?pdp_filters=..., &position=...) que CAMBIAN aunque sea el mismo
#      producto. El historial usa el link como llave para no repetir, así
#      que veía "un producto nuevo" en cada pasada. Ahora se guarda solo
#      la URL sin "?...".
#   2) Dos copias del bot corriendo a la vez (ej: la dejaste corriendo y
#      la volviste a abrir, o vigilante.sh + una corrida manual) hacían
#      que cada copia mandara sus propias alertas sin saber de la otra.
#      Ahora hay un candado (cazador.lock con el PID) que impide que
#      arranque una segunda copia mientras la primera siga viva.
#   3) Si el proceso se cortaba (batería, Android matando la app) justo
#      mientras se guardaba el historial, el archivo podía quedar a medio
#      escribir y corromperse, perdiendo la memoria de qué ya se mandó.
#      Ahora el guardado es "atómico" (escribe en un archivo temporal y
#      recién al final lo reemplaza) y si igual encuentra un historial
#      corrupto, lo respalda como .corrupto y sigue con uno nuevo en vez
#      de crashear cada pasada.
# - ARREGLO 2 de "manda las mismas ofertas" (confirmado en vivo el
#   17-ago con capturas de Ofertas Chile Premium: la misma cama elástica
#   de Paris se mandó 3 veces en menos de un minuto, con una sola copia
#   del bot corriendo): el mismo problema de link volátil del punto (1)
#   también pasa en PARIS (y potencialmente cualquier tienda) — un mismo
#   producto puede aparecer en más de una sección/página con un link que
#   trae un parámetro de posición/tracking distinto cada vez, así que
#   parecía "otro producto" y se mandaba de nuevo, TODO dentro de la
#   misma pasada. Se creó una función compartida normalizar_link() que
#   saca el "?..." de la URL, y se aplicó a TODAS las tiendas (Falabella,
#   Paris, Lider, MercadoLibre, Jumbo, DBS), no solo a MercadoLibre.
#   También se hizo el candado de PID (punto 2 de arriba) atómico de
#   verdad (antes tenía una ventanita de carrera si dos procesos
#   arrancaban justo al mismo tiempo).
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
MINUTOS_ENTRE_PASADAS = 15  # espera del modo bucle entre pasada y pasada
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
# Categorías de Falabella a vigilar (URLs con "/category/"). Se agregaron
# Moda-Mujer, Moda-Hombre y Smart-TV para que no sea puro Camas/Audio.
CATEGORIAS_FALABELLA = [
    "https://www.falabella.com/falabella-cl/category/cat2018/Celulares-y-Telefonos",
    "https://www.falabella.com/falabella-cl/category/cat4830/Zapatillas",
    "https://www.falabella.com/falabella-cl/category/cat2005/Computacion",
    "https://www.falabella.com/falabella-cl/category/cat3205/Perfumes",
    "https://www.falabella.com/falabella-cl/category/cat3145/Camas",
    "https://www.falabella.com/falabella-cl/category/cat2032/Audio",
    "https://www.falabella.com/falabella-cl/category/cat20002/Moda-Mujer",
    "https://www.falabella.com/falabella-cl/category/cat1320008/Moda-Hombre",
    "https://www.falabella.com/falabella-cl/category/cat7190148/Smart-TV",
]
MAX_PAGINAS_FALABELLA = 5
# Secciones de ofertas de Paris a vigilar (antes solo se leía "mujer").
# Se agregaron deportes y belleza para sumar más variedad.
# Para agregar más: paris.cl -> sección -> "Ofertas" y pega la URL aquí.
URLS_OFERTAS_PARIS = [
    "https://www.paris.cl/mujer/ofertas/",
    "https://www.paris.cl/hombre/ofertas/",
    "https://www.paris.cl/tecnologia/ofertas/",
    "https://www.paris.cl/deportes/ofertas/",
    "https://www.paris.cl/belleza/ofertas/",
]
MAX_PAGINAS_PARIS = 4
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
MAX_PAGINAS_EASY = 3
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
    ("Electro", "https://www.lider.cl/browse/liquidacion-lider/electro/95467052_73455141"),
    ("Electrohogar", "https://www.lider.cl/browse/liquidacion-lider/electro/electrohogar/95467052_73455141_77393875"),
    ("Linea-Blanca", "https://www.lider.cl/browse/liquidacion-lider/electro/linea-blanca/95467052_73455141_43302143"),
    ("Muebles", "https://www.lider.cl/browse/liquidacion-lider/muebles/95467052_15955368"),
]
MAX_PAGINAS_LIDER = 5
# Cuántas alertas como máximo se mandan POR CATEGORÍA en cada pasada (ej:
# como mucho 6 camas, 6 refrigeradores, 6 poleras...). Esto evita que una
# categoría con muchísimo stock en oferta (como Camas o Línea Blanca)
# tape a las demás. Se manda primero lo de mejor descuento dentro de cada
# categoría; lo que se queda fuera no se pierde, se vuelve a evaluar en
# la próxima pasada. Los productos de tu lista_deseos.txt NO tienen este
# límite: esos siempre se avisan.
MAX_ALERTAS_POR_CATEGORIA_POR_PASADA = 6
DOMINIO_LIDER = "https://www.lider.cl"
# MERCADOLIBRE — URL verificada con navegador real (ver nota de arriba).
CATEGORIAS_MERCADOLIBRE = [
    "https://www.mercadolibre.cl/ofertas",
]
MAX_PAGINAS_MERCADOLIBRE = 3
DOMINIO_MERCADOLIBRE = "https://www.mercadolibre.cl"
# JUMBO — jumbo-ofertas trae TODO sin filtrar (comida, perecibles, etc.,
# tal como se pidió), a diferencia de Líder que solo trae no-perecibles.
# Cada página pesa ~4-4.5 MB (ver nota de arriba) — MAX_PAGINAS_JUMBO
# controla cuántas de las 97 páginas totales se revisan por pasada.
CATEGORIAS_JUMBO = [
    "https://www.jumbo.cl/jumbo-ofertas",
]
MAX_PAGINAS_JUMBO = 8
DOMINIO_JUMBO = "https://www.jumbo.cl"
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
# Candado para que no queden DOS copias del bot corriendo a la vez (eso
# manda ofertas duplicadas, porque cada copia tiene su propia foto del
# historial en memoria y no se entera de lo que la otra ya mandó).
ARCHIVO_LOCK = "cazador.lock"
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
def normalizar_link(url):
    """
    Quita el fragmento (#...) y los parámetros de la URL (?...) de un link
    de producto. Varias tiendas (MercadoLibre, y según vimos también
    Paris) agregan parámetros de tracking/posición que CAMBIAN aunque sea
    el mismo producto, incluso dentro de la MISMA pasada si el producto
    aparece en más de una sección o página. Como el historial usa el link
    como llave para no repetir ofertas, un link que cambia solo hace que
    el mismo producto se mande varias veces. Nos quedamos solo con la
    parte "de verdad" de la URL (antes del "?").
    """
    if not url:
        return url
    return url.split("#")[0].split("?")[0]
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
    try:
        with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except json.JSONDecodeError:
        # Probablemente Android mató el proceso justo mientras se estaba
        # guardando el archivo, y quedó a medio escribir. En vez de
        # reventar en cada pasada (y no mandar NADA nunca más), lo
        # guardamos como respaldo y arrancamos un historial nuevo.
        respaldo = ARCHIVO_HISTORIAL + ".corrupto"
        print(f"⚠️ {ARCHIVO_HISTORIAL} estaba corrupto (probablemente un corte a medio guardar). Lo dejo como {respaldo} y empiezo un historial nuevo.", flush=True)
        try:
            os.replace(ARCHIVO_HISTORIAL, respaldo)
        except OSError:
            pass
        return {}
def guardar_historial(historial):
    # Escritura atómica: primero a un archivo temporal, y recién al final
    # se reemplaza el archivo real. Así, si el proceso muere a mitad de
    # camino, el historial de verdad nunca queda corrupto a medias.
    archivo_temporal = ARCHIVO_HISTORIAL + ".tmp"
    with open(archivo_temporal, "w", encoding="utf-8") as archivo:
        json.dump(historial, archivo, indent=4, ensure_ascii=False)
    os.replace(archivo_temporal, ARCHIVO_HISTORIAL)
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
                link = normalizar_link(producto.get("url"))
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
                    "categoria": nombre_corto,
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
def procesar_tarjetas_paris(tarjetas, productos_por_link, nombre_corto):
    """Convierte tarjetas de producto de Paris en diccionarios. Devuelve cuántas eran nuevas."""
    nuevos = 0
    for tarjeta in tarjetas:
        link = tarjeta.get("href")
        if not link:
            continue
        if link.startswith("/"):
            link = DOMINIO_PARIS + link
        # Paris agrega parámetros de tracking al link (ej: posición del
        # producto en la grilla) que cambian aunque sea el MISMO producto,
        # incluso si aparece en dos secciones/páginas distintas dentro de
        # la misma pasada. Sin esto, el mismo colchón/cama podía colarse
        # 2-3 veces con links "distintos" y mandarse repetido.
        link = normalizar_link(link)
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
            "categoria": nombre_corto,
            "titulo": titulo,
            "precio_oferta": precio_oferta,
            "precio_normal": precio_normal,
            "descuento": descuento,
            "link": link
        }
        nuevos += 1
    return nuevos
def buscar_ofertas_paris():
    print("🔍 Buscando ofertas en Paris...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for seccion in URLS_OFERTAS_PARIS:
        nombre_corto = seccion.rstrip("/").split("/")[-2] if seccion.rstrip("/").split("/")[-1] == "ofertas" else seccion.rstrip("/").split("/")[-1]
        for numero_pagina in range(1, MAX_PAGINAS_PARIS + 1):
            if numero_pagina == 1:
                url = seccion
            else:
                separador = "&" if "?" in seccion else "?"
                url = f"{seccion}{separador}page={numero_pagina}"
            respuesta = pedir_pagina(url)
            if respuesta is None:
                print(f"   ⚠️ No pude conectarme a {nombre_corto} pág. {numero_pagina}.", flush=True)
                break
            respuesta.encoding = "utf-8"
            if respuesta.status_code != 200:
                print(f"   ⚠️ {nombre_corto} pág. {numero_pagina} respondió código {respuesta.status_code}.", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_diagnostico_bloqueo(respuesta)
                    ya_se_imprimieron_pistas = True
                break
            sopa = BeautifulSoup(respuesta.text, "lxml")
            tarjetas = sopa.find_all("a", id=lambda v: v and v.startswith("product-"))
            if not tarjetas:
                print(f"   ⚠️ {nombre_corto} pág. {numero_pagina}: 0 tarjetas de producto.", flush=True)
                if not ya_se_imprimieron_pistas:
                    imprimir_pistas_pagina(respuesta.text)
                    ya_se_imprimieron_pistas = True
                break
            antes = len(productos_por_link)
            nuevos_en_esta_pagina = procesar_tarjetas_paris(tarjetas, productos_por_link, nombre_corto)
            print(f"   📄 {nombre_corto} pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) nuevo(s) con descuento ({len(tarjetas)} tarjetas en la página).", flush=True)
            if numero_pagina > 1 and len(productos_por_link) == antes:
                # "?page=" probablemente no le hace nada a esta sección: no seguimos gastando pedidos.
                break
            time.sleep(random.uniform(2, 4))
    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Paris.", flush=True)
    return list(productos_por_link.values())
# ---------------------------------------------------------------------
# LECTOR: LIDER (Liquidación Lider — estructura Walmart, con paginación)
# ---------------------------------------------------------------------
def buscar_ofertas_lider():
    print("🔍 Buscando ofertas en Lider...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for nombre_corto, categoria_url in CATEGORIAS_LIDER:
        for numero_pagina in range(1, MAX_PAGINAS_LIDER + 1):
            if numero_pagina == 1:
                url = categoria_url
            else:
                separador = "&" if "?" in categoria_url else "?"
                url = f"{categoria_url}{separador}page={numero_pagina}"
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
                        link = normalizar_link(link)
                        descuento = round((1 - (precio_oferta / precio_normal)) * 100)
                        if link in productos_por_link:
                            continue
                        productos_por_link[link] = {
                            "tienda": "Lider",
                            "categoria": nombre_corto,
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
        nombre_corto = categoria.rstrip("/").split("/")[-1]
        for numero_pagina in range(1, MAX_PAGINAS_EASY + 1):
            if numero_pagina == 1:
                url = categoria
            else:
                separador = "&" if "?" in categoria else "?"
                url = f"{categoria}{separador}page={numero_pagina}"
            try:
                respuesta = pedir_pagina(url)
                if respuesta is None:
                    print(f"   ⚠️ No pude conectarme a cluster {nombre_corto} pág. {numero_pagina} después de varios intentos.", flush=True)
                    break
                if respuesta.status_code != 200:
                    print(f"   ⚠️ No pude acceder a cluster {nombre_corto} pág. {numero_pagina}. Código: {respuesta.status_code}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_diagnostico_bloqueo(respuesta)
                        ya_se_imprimieron_pistas = True
                    break
                datos = extraer_bloque_next_data(respuesta.text)
                if not datos:
                    print(f"   ⚠️ No encontré datos en cluster {nombre_corto} pág. {numero_pagina}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_pistas_pagina(respuesta.text)
                        ya_se_imprimieron_pistas = True
                    break
                productos_crudos = (
                    datos.get("props", {})
                    .get("pageProps", {})
                    .get("serverProductsResponse", {})
                    .get("productList", [])
                )
                if not productos_crudos:
                    print(f"   ⚠️ Cluster {nombre_corto} pág. {numero_pagina} venía sin productos.", flush=True)
                    break
                nuevos_en_esta_pagina = 0
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
                        "categoria": f"cluster-{nombre_corto}",
                        "titulo": titulo,
                        "precio_oferta": precio_oferta,
                        "precio_normal": precio_normal,
                        "descuento": descuento,
                        "link": link
                    }
                    nuevos_en_esta_pagina += 1
                print(f"   📄 Cluster {nombre_corto} pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) nuevo(s) con descuento ({len(productos_crudos)} en la página).", flush=True)
                if numero_pagina > 1 and nuevos_en_esta_pagina == 0:
                    # "?page=" probablemente no le hace nada a este cluster: no seguimos gastando pedidos.
                    break
            except Exception as error:
                print(f"   ⚠️ Error en cluster {nombre_corto} pág. {numero_pagina}: {error}", flush=True)
                break
            time.sleep(random.uniform(2, 4))
    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Easy.", flush=True)
    return list(productos_por_link.values())
# ---------------------------------------------------------------------
# LECTOR: MERCADOLIBRE (EXPERIMENTAL — ver notas al inicio del archivo)
# ---------------------------------------------------------------------
def limpiar_precio_mercadolibre(texto):
    texto = re.sub(r"[^0-9]", "", texto or "")
    return int(texto) if texto else None
def procesar_tarjeta_mercadolibre(tarjeta):
    # ML ha rediseñado sus tarjetas de producto varias veces ("poly-card"
    # es el diseño más nuevo, "ui-search-result" el clásico). Probamos
    # ambos vocabularios de clases para no depender de uno solo.
    enlace = tarjeta.find("a", class_=lambda c: c and ("poly-component__title" in c or "ui-search-link" in c or "ui-search-item__title" in c))
    if not enlace:
        enlace = tarjeta.find("a", href=True)
    if not enlace or not enlace.get("href"):
        return None
    link = normalizar_link(enlace["href"])
    titulo = reparar_texto(enlace.get_text(strip=True))
    if not titulo:
        titulo_tag = tarjeta.find(class_=lambda c: c and "title" in c)
        titulo = reparar_texto(titulo_tag.get_text(strip=True)) if titulo_tag else None
    if not titulo:
        return None
    precio_normal = None
    precio_oferta = None
    # Precio tachado (normal): suele venir dentro de <s> o con "previous" en la clase.
    tachado = tarjeta.find(["s", "del"])
    if not tachado:
        tachado = tarjeta.find(class_=lambda c: c and "previous" in c)
    if tachado:
        fraccion = tachado.find(class_=lambda c: c and "andes-money-amount__fraction" in c)
        precio_normal = limpiar_precio_mercadolibre(fraccion.get_text() if fraccion else tachado.get_text())
    # Todas las fracciones de precio en la tarjeta; la que no está tachada es la oferta.
    fracciones = tarjeta.find_all(class_=lambda c: c and "andes-money-amount__fraction" in c)
    for fraccion in fracciones:
        if tachado and fraccion in tachado.find_all(class_=lambda c: c and "andes-money-amount__fraction" in c):
            continue
        valor = limpiar_precio_mercadolibre(fraccion.get_text())
        if valor:
            precio_oferta = valor
            break
    if not precio_normal or not precio_oferta or precio_oferta >= precio_normal:
        return None
    if link.startswith("/"):
        link = DOMINIO_MERCADOLIBRE + link
    descuento = round((1 - (precio_oferta / precio_normal)) * 100)
    return {
        "tienda": "MercadoLibre",
        "categoria": "General",
        "titulo": titulo,
        "precio_oferta": precio_oferta,
        "precio_normal": precio_normal,
        "descuento": descuento,
        "link": link
    }
def buscar_ofertas_mercadolibre():
    print("🔍 Buscando ofertas en MercadoLibre...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for categoria in CATEGORIAS_MERCADOLIBRE:
        for numero_pagina in range(1, MAX_PAGINAS_MERCADOLIBRE + 1):
            if numero_pagina == 1:
                url = categoria
            else:
                separador = "&" if "?" in categoria else "?"
                url = f"{categoria}{separador}page={numero_pagina}"
            try:
                respuesta = pedir_pagina(url)
                if respuesta is None:
                    print(f"   ⚠️ No pude conectarme a MercadoLibre pág. {numero_pagina} después de varios intentos.", flush=True)
                    break
                if respuesta.status_code != 200:
                    print(f"   ⚠️ No pude acceder a MercadoLibre pág. {numero_pagina}. Código: {respuesta.status_code}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_diagnostico_bloqueo(respuesta)
                        ya_se_imprimieron_pistas = True
                    break
                sopa = BeautifulSoup(respuesta.text, "lxml")
                tarjetas = sopa.find_all(class_=lambda c: c and ("poly-card" in c or "ui-search-result__wrapper" in c))
                if not tarjetas:
                    print(f"   ⚠️ MercadoLibre pág. {numero_pagina}: 0 tarjetas encontradas con los selectores actuales.", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_pistas_pagina(respuesta.text)
                        print(f"   🔬 Pistas ML: ¿contiene 'poly-card'? -> {'poly-card' in respuesta.text} | ¿contiene 'ui-search-result'? -> {'ui-search-result' in respuesta.text}", flush=True)
                        ya_se_imprimieron_pistas = True
                    break
                nuevos_en_esta_pagina = 0
                for tarjeta in tarjetas:
                    try:
                        producto = procesar_tarjeta_mercadolibre(tarjeta)
                    except Exception:
                        producto = None
                    if not producto or producto["link"] in productos_por_link:
                        continue
                    productos_por_link[producto["link"]] = producto
                    nuevos_en_esta_pagina += 1
                print(f"   📄 MercadoLibre pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) nuevo(s) con descuento ({len(tarjetas)} tarjetas en la página).", flush=True)
                if numero_pagina > 1 and nuevos_en_esta_pagina == 0:
                    break
            except Exception as error:
                print(f"   ⚠️ Error en MercadoLibre pág. {numero_pagina}: {error}", flush=True)
                break
            time.sleep(random.uniform(2, 4))
    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en MercadoLibre.", flush=True)
    return list(productos_por_link.values())
# ---------------------------------------------------------------------
# LECTOR: JUMBO (jumbo-ofertas — ver nota grande al inicio del archivo)
# ---------------------------------------------------------------------
REGEX_LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
REGEX_CHUNK_NEXT_F = re.compile(r'self\.__next_f\.push\(\[\d+,"((?:\\.|[^"\\])*)"\]\)')
REGEX_PRODUCTO_JUMBO = re.compile(r'"price":(\d+),"listPrice":(\d+)((?:(?!"price").)*?)"name":"((?:[^"\\]|\\.)*)"', re.S)
def extraer_mapa_nombre_url_jumbo(html):
    """Lee los <script type="application/ld+json"> y arma un {nombre: url}."""
    mapa = {}
    for bloque in REGEX_LDJSON.findall(html):
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        for item in datos.get("itemListElement", []) or []:
            nombre = item.get("name")
            url = item.get("url")
            if nombre and url:
                mapa[nombre] = url
    return mapa
def extraer_productos_jumbo(html):
    """
    Los precios de Jumbo vienen repartidos en varios <script>self.__next_f.push([...])
    (formato interno de Next.js), como JSON escapado dentro de un string.
    Se desescapan todos los pedazos, se pegan, y se buscan los patrones
    "price":X,"listPrice":Y...,"name":"..." adentro. Devuelve una lista
    de (precio_oferta, precio_normal, nombre).
    """
    pedazos = []
    for coincidencia in REGEX_CHUNK_NEXT_F.finditer(html):
        try:
            pedazos.append(json.loads('"' + coincidencia.group(1) + '"'))
        except (json.JSONDecodeError, ValueError):
            continue  # pedazo mal formado: se ignora, no se revienta el resto
    texto_completo = "\n".join(pedazos)
    productos = []
    for m in REGEX_PRODUCTO_JUMBO.finditer(texto_completo):
        try:
            precio_oferta = int(m.group(1))
            precio_normal = int(m.group(2))
            nombre = json.loads('"' + m.group(4) + '"')
        except (json.JSONDecodeError, ValueError):
            continue
        productos.append((precio_oferta, precio_normal, nombre))
    return productos
def buscar_ofertas_jumbo():
    print("🔍 Buscando ofertas en Jumbo...", flush=True)
    productos_por_link = {}
    ya_se_imprimieron_pistas = False
    for categoria in CATEGORIAS_JUMBO:
        for numero_pagina in range(1, MAX_PAGINAS_JUMBO + 1):
            if numero_pagina == 1:
                url = categoria
            else:
                separador = "&" if "?" in categoria else "?"
                url = f"{categoria}{separador}page={numero_pagina}"
            try:
                respuesta = pedir_pagina(url)
                if respuesta is None:
                    print(f"   ⚠️ No pude conectarme a Jumbo pág. {numero_pagina} después de varios intentos.", flush=True)
                    break
                if respuesta.status_code != 200:
                    print(f"   ⚠️ No pude acceder a Jumbo pág. {numero_pagina}. Código: {respuesta.status_code}", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_diagnostico_bloqueo(respuesta)
                        ya_se_imprimieron_pistas = True
                    break
                mapa_url = extraer_mapa_nombre_url_jumbo(respuesta.text)
                crudos = extraer_productos_jumbo(respuesta.text)
                if not mapa_url and not crudos:
                    print(f"   ⚠️ Jumbo pág. {numero_pagina}: no encontré ni el bloque ld+json ni los chunks de Next.js.", flush=True)
                    if not ya_se_imprimieron_pistas:
                        imprimir_pistas_pagina(respuesta.text)
                        print(f"   🔬 Pistas Jumbo: ¿contiene 'application/ld+json'? -> {'application/ld+json' in respuesta.text} | ¿contiene 'self.__next_f.push'? -> {'self.__next_f.push' in respuesta.text}", flush=True)
                        ya_se_imprimieron_pistas = True
                    break
                nuevos_en_esta_pagina = 0
                sin_url = 0
                for precio_oferta, precio_normal, nombre in crudos:
                    if precio_oferta >= precio_normal or precio_normal == 0:
                        continue
                    link = normalizar_link(mapa_url.get(nombre))
                    if not link:
                        sin_url += 1
                        continue
                    if link in productos_por_link:
                        continue
                    descuento = round((1 - (precio_oferta / precio_normal)) * 100)
                    productos_por_link[link] = {
                        "tienda": "Jumbo",
                        "categoria": "General",
                        "titulo": reparar_texto(nombre),
                        "precio_oferta": precio_oferta,
                        "precio_normal": precio_normal,
                        "descuento": descuento,
                        "link": link
                    }
                    nuevos_en_esta_pagina += 1
                print(f"   📄 Jumbo pág. {numero_pagina}: {nuevos_en_esta_pagina} producto(s) nuevo(s) con descuento ({len(crudos)} con precio/precio-lista, {sin_url} sin link).", flush=True)
                if len(crudos) == 0:
                    break
            except Exception as error:
                print(f"   ⚠️ Error en Jumbo pág. {numero_pagina}: {error}", flush=True)
                break
            time.sleep(random.uniform(2, 4))
    print(f"   ✅ {len(productos_por_link)} producto(s) único(s) en Jumbo.", flush=True)
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
    link = normalizar_link(enlace_nombre.get("href"))
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
        "categoria": "General",
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
def califica_para_enviar(producto, historial, lista_deseos):
    """
    Decide si un producto merece avisarse (nuevo, o bajó de precio de nuevo).
    NO envía nada todavía — solo evalúa. De paso marca producto["deseo"].
    """
    descuento = producto["descuento"]
    link = producto["link"]
    deseo = buscar_deseo(producto["titulo"], lista_deseos) if lista_deseos else None
    producto["deseo"] = deseo
    umbral = DESCUENTO_MINIMO_DESEOS if deseo else DESCUENTO_MINIMO_GRATIS
    if descuento < umbral:
        return False
    registro_anterior = historial.get(link)
    if registro_anterior is None:
        return True
    if producto["precio_oferta"] < registro_anterior["precio_oferta"]:
        return True
    return False
def enviar_producto(producto, historial):
    """Manda la alerta a Telegram y, si se pudo, deja registro en el historial."""
    descuento = producto["descuento"]
    es_premium = descuento >= DESCUENTO_MINIMO_PREMIUM
    chat_id = TELEGRAM_CHAT_ID_PREMIUM if es_premium else TELEGRAM_CHAT_ID_GRATIS
    marca_deseo = " 🎯" if producto.get("deseo") else ""
    print(f"🆕 Enviando{marca_deseo} [{producto['tienda']}/{producto.get('categoria', 'General')}]: {producto['titulo']} ({descuento}%)", flush=True)
    se_envio = enviar_alerta_telegram(producto, chat_id, es_premium)
    if se_envio:
        historial[producto["link"]] = {"precio_oferta": producto["precio_oferta"], "canal": "premium" if es_premium else "gratis"}
    time.sleep(SEGUNDOS_ENTRE_MENSAJES)
    return se_envio
def repartir_cupo_por_categoria(candidatos):
    """
    Agrupa los candidatos por (tienda, categoria) y deja pasar como mucho
    MAX_ALERTAS_POR_CATEGORIA_POR_PASADA de cada grupo, priorizando el
    mayor descuento. Así ninguna categoría (ej: Camas) tapa a las demás.
    Los productos de la lista de deseos se saltan el límite: siempre pasan.
    """
    con_deseo = [p for p in candidatos if p.get("deseo")]
    sin_deseo = [p for p in candidatos if not p.get("deseo")]
    grupos = {}
    for producto in sin_deseo:
        clave = (producto["tienda"], producto.get("categoria", "General"))
        grupos.setdefault(clave, []).append(producto)
    seleccionados = list(con_deseo)
    for (tienda, categoria), productos_grupo in grupos.items():
        productos_grupo.sort(key=lambda p: p["descuento"], reverse=True)
        elegidos = productos_grupo[:MAX_ALERTAS_POR_CATEGORIA_POR_PASADA]
        seleccionados.extend(elegidos)
        sobrantes = len(productos_grupo) - len(elegidos)
        if sobrantes > 0:
            print(f"   ⏸️ {tienda}/{categoria}: {sobrantes} oferta(s) más quedan en cola para la próxima pasada (cupo de {MAX_ALERTAS_POR_CATEGORIA_POR_PASADA} lleno).", flush=True)
    random.shuffle(seleccionados)  # para que el canal no salga "10 camas seguidas"
    return seleccionados
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
    time.sleep(3)
    todos_los_productos += buscar_ofertas_mercadolibre()
    time.sleep(3)
    todos_los_productos += buscar_ofertas_jumbo()
    print(f"\n📦 Total combinado: {len(todos_los_productos)} producto(s).\n", flush=True)
    historial = cargar_historial()
    candidatos = [p for p in todos_los_productos if califica_para_enviar(p, historial, lista_deseos)]
    print(f"🔎 {len(candidatos)} producto(s) califican para avisar (antes de repartir el cupo por categoría).", flush=True)
    a_enviar = repartir_cupo_por_categoria(candidatos)
    enviados = 0
    for producto in a_enviar:
        if enviar_producto(producto, historial):
            enviados += 1
            guardar_historial(historial)
    print(f"\n✅ Pasada lista. Se enviaron {enviados} alerta(s) de {len(candidatos)} que calificaban.", flush=True)
def activar_candado_energia():
    """En Termux, evita que Android duerma el proceso con la pantalla apagada."""
    try:
        subprocess.run(["termux-wake-lock"], timeout=5)
        print("🔒 Candado de energía activado (termux-wake-lock).", flush=True)
    except Exception:
        pass
def _pid_esta_vivo(pid):
    # En Linux/Termux, /proc/<pid> solo existe si ese proceso sigue vivo.
    return os.path.exists(f"/proc/{pid}")
def hay_otro_proceso_corriendo():
    """
    Revisa si ARCHIVO_LOCK existe Y si el PID que dice adentro sigue vivo.
    Dos copias del bot corriendo a la vez es otra forma de mandar ofertas
    duplicadas: cada copia carga su propia versión del historial en
    memoria al empezar, así que ninguna de las dos se entera de lo que la
    otra ya mandó, y las dos terminan avisando lo mismo.
    """
    if not os.path.exists(ARCHIVO_LOCK):
        return False
    try:
        with open(ARCHIVO_LOCK, "r", encoding="utf-8") as archivo:
            pid_anterior = int(archivo.read().strip())
    except (ValueError, OSError):
        # El lock está corrupto/vacío: lo tratamos como si no existiera.
        return False
    return _pid_esta_vivo(pid_anterior)
def tomar_lock():
    """
    Crea ARCHIVO_LOCK de forma ATÓMICA (abre con O_CREAT|O_EXCL: falla si
    el archivo ya existe). Esto cierra una ventana de carrera: si dos
    procesos arrancan casi al mismo tiempo, "revisar si el lock existe" y
    "escribir el lock" NO pueden pisarse entre sí como pasaría con un
    simple if-existe / escribir por separado.
    Si el archivo ya existe pero el PID de adentro está muerto (quedó
    "pegado" de una corrida anterior que no se cerró bien), lo limpiamos y
    reintentamos una vez.
    """
    for intento in range(2):
        try:
            fd = os.open(ARCHIVO_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as archivo:
                archivo.write(str(os.getpid()))
            return True
        except FileExistsError:
            if hay_otro_proceso_corriendo():
                return False
            # Lock viejo/huérfano (proceso muerto): lo limpiamos y reintentamos.
            try:
                os.remove(ARCHIVO_LOCK)
            except OSError:
                pass
    return False
def liberar_lock():
    try:
        os.remove(ARCHIVO_LOCK)
    except OSError:
        pass
if __name__ == "__main__":
    print("=" * 50, flush=True)
    print(f"🤖 Modo de ejecución: {MODO.upper()}", flush=True)
    print(f"🗂️ Cuaderno de memoria: {ARCHIVO_HISTORIAL}", flush=True)
    if not tomar_lock():
        print("⛔ Ya hay OTRA copia de cazador_ofertas.py corriendo (mismo cuaderno de", flush=True)
        print("   memoria). Para no mandar ofertas duplicadas, esta copia se cierra sin", flush=True)
        print("   hacer nada. Si estás seguro de que no hay otra corriendo, borra el", flush=True)
        print(f"   archivo '{ARCHIVO_LOCK}' y vuelve a intentar.", flush=True)
        sys.exit(1)
    try:
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
    finally:
        liberar_lock()
