══════════════════════════════════════════════════════════
      AI Prompt Vault  v3.1.0
      Organiza tus obras de arte con IA (imágenes de referencia + prompts + modelos)
      Interfaz disponible en 中文 / English / Español / 日本語
══════════════════════════════════════════════════════════

【Introducción】
Una herramienta local para Windows, totalmente sin conexión y
con interfaz propia, para reunir y organizar obras de arte
generadas por IA: guarda imágenes de referencia, extrae prompts
automáticamente, anota todos los modelos, filtra por familia de
modelo base, gestiona grupos personalizados y permite ver las
salidas de ComfyUI directamente en la galería. Desde v3.1.0 la
interfaz está disponible en cuatro idiomas — chino, inglés,
español y japonés — y se puede cambiar en cualquier momento.

──────────────────────────────────────────────
1. Requisitos del sistema e instalación
──────────────────────────────────────────────
· Windows 10 / Windows 11 (64 bits)
· No necesita instalar nada: es un único archivo .exe portátil,
  haga doble clic para usarlo
· Totalmente sin conexión (solo la importación de enlaces de
  Civitai y la descarga de modelos requieren Internet)

【Aviso de SmartScreen en el primer inicio】
Como la aplicación no tiene certificado de firma de código,
Windows puede mostrar "Windows protegió su PC" en el primer
inicio. Es normal: haga clic en:
    Más información → Ejecutar de todas formas
La aplicación se abrirá con normalidad. (Solo la primera vez.)

【Cambiar el idioma de la interfaz】
Ajustes → Idioma de la interfaz: elija 中文 / English /
Español / 日本語. Reinicie la aplicación para aplicar el cambio;
su preferencia se guarda automáticamente.
(La preferencia de idioma se guarda en la biblioteca y viaja
con sus datos.)

──────────────────────────────────────────────
2. Guía de funciones
──────────────────────────────────────────────

【Colección (cómo añadir imágenes)】
· Arrastrar y soltar imágenes: arrastre imágenes de referencia
  de la web directamente a la zona punteada (varias a la vez);
  también funcionan los archivos de imagen locales
· Pegar imágenes: pulse Ctrl+V en cualquier lugar, o haga clic
  en el botón "Pegar imagen"
· Vídeos locales: importe archivos de vídeo locales (se extrae
  automáticamente una miniatura del primer fotograma)
· Importación por enlace de Civitai: pegue un enlace de
  imagen / modelo / vídeo de civitai.com o civitai.red →
  "Analizar e importar", que extrae automáticamente:
  - Prompt positivo / negativo
  - Familia del modelo base (Krea 2 / Flux.1 / Flux.2 / SDXL /
    Pony / Illustrious / NoobAI / SD 1.5 / SD 3.5, etc.)
  - La lista completa de modelos (Checkpoint / LoRA / Embedding /
    VAE, etc.), cada uno con su enlace de página de Civitai:
    haga clic en "Abrir" para ir directamente
  - Muestreador, pasos, CFG, semilla, tamaño de la imagen
  - Descarga automática de la imagen original; en el caso de
    enlaces de vídeo, se descarga el vídeo y se genera una
    miniatura del primer fotograma para la galería
  Consejo: puede pegar varios enlaces a la vez (separados por
  espacios o saltos de línea).

【Extracción automática de parámetros de PNG locales (importante)】
Los PNG exportados desde SD WebUI (A1111), ComfyUI o NovelAI
incluyen sus parámetros de generación incrustados. Al arrastrar
o pegar una imagen así, la aplicación rellena automáticamente:
prompt positivo/negativo, muestreador, pasos, CFG, semilla,
nombre del modelo y LoRA (la barra de estado muestra "Prompt
incrustado extraído automáticamente ✓").

【Galería de salidas de ComfyUI (Mis Obras)】
En Ajustes puede añadir una o varias "Carpetas de salida de
ComfyUI" (múltiples carpetas, en lugar de la antigua
ruta de salida unida automáticamente). Los cambios se aplican
inmediatamente al guardar; la aplicación escanea estas carpetas
(incluidos todos los subdirectorios) en segundo plano y añade
las imágenes generadas a la galería como "referencias
virtuales": no copia archivos ni ocupa espacio extra:
· Aparece el grupo "Mis Obras" en el árbol de grupos; con varias
  carpetas de salida, las obras se agrupan automáticamente como
  Mis Obras / <nombre de carpeta> / <subcarpeta>
· Los parámetros de generación se extraen automáticamente de
  cada obra (prompt / muestreador / modelo / LoRA, etc.)
· Caché en disco: el primer escaneo se guarda en caché, así el
  inicio carga en segundos; las miniaturas tienen su propia
  caché
· Escaneo más rápido: análisis paralelo multihilo — medido en
  4.877 imágenes, de ~4,5 minutos a ~45 segundos, unas 6,5 veces
  más rápido
· La caché con directorio desajustado se invalida y se vuelve a
  escanear automáticamente
· Sin escaneos congelados: los hilos de escaneo antiguos se
  limpian y hay un respaldo por tiempo de espera
· Límite de renderizado para evitar bloqueos: cuando hay muchas
  obras virtuales solo se muestran las primeras N; las galerías
  grandes se renderizan por lotes, la ventana sigue respondiendo
  y las imágenes aparecen poco a poco
· Botón "Actualizar" en la barra de herramientas de la galería:
  cuando aparezcan imágenes nuevas en las carpetas de salida,
  haga clic para lanzar   un nuevo escaneo en segundo plano (sin vigilancia
  en tiempo real, para ahorrar recursos)
· Marca "Archivo faltante": las obras cuyo archivo de origen se
  haya movido o eliminado se marcan claramente en la galería
· Al guardar los ajustes, la galería se actualiza de inmediato,
  con el aviso "Escaneando las carpetas de salida en segundo
  plano..."
· Haga doble clic en una obra virtual para ver los detalles;
  nunca se copia en la biblioteca (evita duplicar el uso del
  disco)

【Navegación por la galería】
· Dos modos de vista:
  - Cuadrícula: miniaturas grandes; arrastre el control
    "Tamaño" para escalar las celdas
  - Lista: tabla de detalles similar a un administrador de
    archivos (miniatura / título / modelo base / modelos /
    prompt / tamaño / fecha de importación); haga clic en las
    cabeceras para ordenar y arrastre los separadores para
    ajustar el ancho
· Orden por: fecha de importación / título / modelo base /
  modelo / tamaño, ascendente o descendente (en modo Lista
  también se ordena con las cabeceras)
· Filtros: familia de modelo base, relación de aspecto, LoRA
  utilizado, origen y búsqueda por palabra clave (busca nombres
  de modelos / familia de modelo base)
· Al pasar el cursor sobre una imagen: aparece una vista previa
  grande y limpia
· Al seleccionar una imagen: el panel derecho muestra los
  detalles completos (imagen grande, prompts, parámetros de
  muestreo, enlaces de modelos, grupo) con copia con un clic de
  todo / positivo / negativo
· Clic derecho en una imagen: copiar prompt, añadir a grupo,
  abrir la página del modelo base, mostrar en carpeta, eliminar
  registro
· Doble clic en una imagen: abre el diálogo de detalles/edición
  para modificar información, copiar o eliminar

【Grupos manuales】
En el área "Grupos de imágenes" bajo la barra lateral izquierda:
· Haga clic en "＋ Nuevo" para crear un grupo personalizado
  (renombrar / eliminar en cualquier momento)
· Clic derecho en una imagen → "Añadir a grupo ▸" para elegir
  un grupo, o "Quitar del grupo"
· Haga clic en un nombre de grupo para ver solo las imágenes de
  ese grupo (con contador)
· Los datos de los grupos se guardan en la biblioteca y
  sobreviven a la migración de equipo

【Operaciones por lotes / Exportación】
Con varias imágenes seleccionadas puede:
· Mover a un grupo / eliminación en lote (van a la papelera)
· Exportación en lote: CSV o Markdown, registros completos o
  solo prompts
· El contenido exportado incluye: título, prompt, lista de
  modelos, parámetros, enlace de origen, etc.

【Detección de duplicados】
· Con un clic encuentra imágenes visualmente duplicadas (hash
  perceptual); compare las vistas previas y conserve la más
  nítida — el resto se mueve a la papelera
· Corregido: "duplicados eliminados que reaparecen tras
  reiniciar": la eliminación se escribe en el índice, así que
  desaparecen para siempre.

【Múltiples bibliotecas】
· Ajustes → Ubicación de la biblioteca → Cambiar, para apuntar
  a un nuevo directorio de biblioteca; reinicie para aplicarlo,
  los datos antiguos se mantienen intactos
· Las bibliotecas son independientes entre sí — ideal para
  mantener separados distintos temas

【Tema claro / oscuro】
· Ajustes → Tema: cambie entre Oscuro / Claro, se aplica
  inmediatamente

【Importación con un clic de la galería de A1111】
· Ajustes → Carpeta de outputs de A1111 (opcional). Una vez
  configurada, importe con un clic las imágenes generadas por
  Automatic1111 (con parámetros de prompt) a la biblioteca; los
  duplicados se omiten automáticamente

【Comprobación de salud de los modelos】
La página Modelos escanea las carpetas de modelos de ComfyUI
(incluidos los subdirectorios) y comprueba la salud de los
archivos (corruptos / de 0 bytes / restos .part). Los modelos
con problemas se marcan con ⚠ rojo y la barra de herramientas
muestra el total. (Los archivos .txt de descripción
se ignoran automáticamente.)

【Descarga de modelos a ComfyUI】
· Ajustes → Carpeta raíz de ComfyUI (un ajuste independiente,
  usado solo para descargar modelos — no interfiere
  con las carpetas de salida)
· Haga clic en "Descargar modelos" en la galería / panel de
  detalles para descargar los modelos de una imagen directamente
  a las carpetas de modelos correspondientes de ComfyUI
· La página Descargas muestra el progreso, pausa / reanuda e
  historial
· Si una descarga falla con 403 / páginas de error HTML, añada
  una API Key de Civitai en Ajustes (generada en el centro de
  usuario de civitai.red) y reintente

──────────────────────────────────────────────
3. Gestión de datos
──────────────────────────────────────────────
Todos los datos se guardan automáticamente en la subcarpeta
Library junto al exe (se crea en el primer inicio; una carpeta
antigua con nombre chino "资料库" se migra automáticamente):

    Library/
    ├── library.db                # Base de datos SQLite (registros/grupos/ajustes)
    ├── settings.json             # Ajustes (idioma, tema, rutas, etc.)
    ├── images/                   # Imágenes originales
    ├── videos/                   # Vídeos importados
    ├── thumbs/                   # Miniaturas (navegación más rápida)
    ├── comfy_output_cache.json   # Caché de escaneo de "Mis Obras"
    ├── comfy_output_thumbs/      # Miniaturas de "Mis Obras"
    └── trash/                    # Papelera (registros eliminados)

· El botón "Abrir carpeta de la biblioteca" de la barra lateral
  la abre directamente
· Copie toda la carpeta Library para hacer una copia de
  seguridad / migrar todo
· Los registros eliminados van a la papelera, nunca se borran
  físicamente de inmediato
· Múltiples bibliotecas: apunte Ajustes a un nuevo directorio
  (reinicio para aplicarlo; los datos de la biblioteca antigua
  no se tocan)
· Tema: cambie Oscuro / Claro en Ajustes (se aplica de inmediato)

──────────────────────────────────────────────
4. Preguntas frecuentes
──────────────────────────────────────────────
· La importación de Civitai a veces falla: el acceso a Civitai
  puede ser inestable; la aplicación cambia automáticamente
  entre civitai.com y civitai.red y reintenta — inténtelo de
  nuevo más tarde
· No puedo arrastrar imágenes desde la web: si hay protección
  antienlaces, guarde la imagen primero y arrastre el archivo
  local
· Cambiar de ordenador: copie toda la carpeta Library y abra la
  aplicación — todo está ahí
· "Mis Obras" no aparece: asegúrese de que las "Carpetas de
  salida de ComfyUI" en Ajustes son correctas; el primer
  escaneo se hace en segundo plano, espere un momento — o haga
  clic en "Actualizar" en la barra de herramientas de la galería
  para forzar un escaneo
· "Mis Obras" marcadas como "Archivo faltante": el archivo de
  origen se movió o eliminó — la galería solo referencia la ruta
  original, revise la carpeta de salida
· ¿El escaneo tarda mucho? El análisis multihilo
  es mucho más rápido (medido ~45 s para 4.877 imágenes). Para
  carpetas muy grandes, el primer escaneo puede tardar algo; la
  interfaz sigue respondiendo
· La descarga de modelos muestra 403 / página de error HTML:
  añada una API Key de Civitai en Ajustes (centro de usuario de
  civitai.red → API Keys) y reintente

──────────────────────────────────────────────
5. Historial de versiones
──────────────────────────────────────────────
v3.1.0  (versión actual — todas las mejoras desde v3.0)
        · Importación de enlaces de vídeo de Civitai (descarga
          del vídeo + extracción de parámetros + miniatura del
          primer fotograma)
        · Interfaz en español / japonés (cuatro idiomas)
        · Galería de salidas de ComfyUI "Mis Obras" (referencias
          virtuales sin copiar archivos; agrupación automática
          con varias carpetas de salida; caché en disco para un
          inicio en segundos; escaneo ~6,5 veces más rápido)
        · Ajustes: múltiples "Carpetas de salida de ComfyUI" +
          fila independiente para la "Carpeta raíz de ComfyUI"
        · Correcciones: los duplicados eliminados ya no reaparecen
          al reiniciar, la galería se actualiza al guardar, sin
          escaneos congelados y una caché con directorio
          desajustado ya no provoca un escaneo completo en cada
          inicio
        · Renderizado por lotes de la galería (las galerías
          grandes siguen respondiendo, las imágenes aparecen poco
          a poco) + botón "Actualizar"
v3.0    Reescritura: base de datos SQLite, múltiples bibliotecas,
        operaciones por lotes y exportación (CSV/Markdown),
        sistema de etiquetas, detección de imágenes duplicadas,
        importación con un clic de salidas de A1111, temas
        claro/oscuro
v2.2.1  Correcciones: importación atascada en "Importando...",
        orden incorrecto, texto en la columna de miniaturas,
        texto de botón recortado; barra de herramientas en dos
        filas
v2.2.0  Nuevo: extracción automática de parámetros de generación
        de imágenes locales (A1111/ComfyUI/NovelAI); rediseño
        completo de la interfaz estilo Apple; barra de grupos
        mejorada
v2.1.x  Nuevo: vista de lista, ordenación, grupos manuales,
        copia con un clic, panel de detalles a la derecha
v2.0    Taxonomía de modelos: familia de modelo base + lista
        completa de modelos + hipervínculos de Civitai por modelo
v1.0.3  Funciones básicas: colección / navegación / filtros /
        importar-exportar

══════════════════════════════════════════════════════════
  ¡Que lo disfrutes! Cualquier comentario es bienvenido.
══════════════════════════════════════════════════════════
