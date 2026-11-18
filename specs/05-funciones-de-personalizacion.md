# SPEC 05 — Funciones de personalización

> **Estado:** Implementado
>
> **Depende de:** SPEC 03 — Actividades de Godot
>
> **Fecha:** 2026-11-18
>
> **Objetivo:** Permitir personalizar tipografía, colores y volumen desde un panel y escuchar los bloques de texto HTML de la plataforma.

## Alcance

- Rama `spec-05-funciones-de-personalizacion`, creada desde `spec-03-actividades-de-godot`.
- Botón Configuración en el encabezado y acceso desde Accesibilidad. Panel modal lateral operable con teclado y cierre con Escape.
- Fuente habitual, Arial, Verdana y OpenDyslexic servida localmente. Tamaño ajustable entre 50 y 300 %.
- Cinco paletas y selectores independientes para encabezado, cuerpo y pie de página. El texto de cada zona se ajusta a blanco o negro según el contraste de su fondo.
- Volumen separado para lectura y actividades/multimedia, entre 0 y 100 %. Cero silencia el canal.
- Botones de bocina junto a títulos, párrafos, elementos de listas, etiquetas y otros bloques de texto. Inician o detienen la lectura del bloque seleccionado mediante SpeechSynthesis.
- Los datos de cuenta, correo, rol, sesión y etiquetas «Próximamente» quedan excluidos de los botones de lectura.
- La lectura comienza por acción del usuario, prioriza voces locales en español y comunica errores o falta de soporte del navegador.
- Las preferencias se almacenan en sessionStorage con una clave vinculada a la sesión autenticada. Se conservan al navegar y recargar la misma pestaña. Se ofrece restablecer valores.
- El volumen de Godot se transmite al iframe mediante postMessage. El receptor valida el emisor y el intervalo del volumen. Un GainNode regula las conexiones Web Audio hacia la salida.
- El puente de audio se inserta al servir el HTML y usa la misma autorización y enlaces firmados que los archivos del Spec 3.

## Límites

La tipografía y los botones de lectura actúan sobre el HTML de la plataforma. Los textos dibujados dentro del Canvas de Godot requieren una integración específica de cada actividad. Las voces disponibles dependen del navegador y del sistema operativo.

## Verificación

- [x] La rama conserva el historial del Spec 3.
- [x] Abrir y cerrar el panel con teclado funciona y el foco regresa al botón de apertura.
- [x] Cambiar la fuente aplica la tipografía elegida y OpenDyslexic carga desde los estáticos locales.
- [x] Cada selector de color afecta a su región y cada paleta ajusta las tres regiones.
- [x] Navegar, recargar y restablecer valores conserva o recupera la configuración esperada.
- [x] Cada bloque legible ofrece un botón accesible que permite iniciar y detener su lectura.
- [x] Los volúmenes de voz y actividad se controlan de forma independiente y admiten cero.
- [x] El puente de Godot conserva la autorización de los paquetes y el aislamiento del iframe.
- [x] La interfaz se mantiene utilizable en móvil.

Las 120 pruebas de cuentas y actividades pasaron en PostgreSQL local el 2026-11-18. El esquema temporal se eliminó al finalizar. Se comprobó el puente de audio con conexiones Web Audio simuladas, incluidos el emisor de mensajes y el silencio. En el navegador se verificaron OpenDyslexic, la paleta oscura y un color personalizado, texto al 150 %, persistencia, restablecimiento, lectura completa y detención, retorno del foco tras Escape y ausencia de desbordamiento en una pantalla de 390 píxeles. El contador Godot siguió funcionando con el puente de audio inyectado.

El rango se amplió después a 50–300 %. Se comprobaron ambos extremos, la persistencia de 300 % al recargar y las exclusiones de lectura en cuenta, rol y estado. Se ajustaron los controles para permitir utilizar el panel en móvil con la ampliación máxima.
