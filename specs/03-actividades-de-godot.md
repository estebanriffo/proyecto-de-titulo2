# SPEC 03 — Actividades de Godot

> **Estado:** Implementado
>
> **Depende de:** SPEC 02 — Página principal por rol
>
> **Fecha:** 2026-11-15
>
> **Objetivo:** Cargar exportaciones Web de Godot desde la página y ofrecer a los alumnos autorizados un catálogo de actividades con portada, nombre y descripción.

## Alcance

- Rama `spec-03-actividades-de-godot` creada desde la rama del Spec 2, conservando su código y diseño.
- Docentes y administradores pueden subir un ZIP exportado para Web, una imagen de portada, un nombre y una descripción breve.
- La carga crea un borrador con previsualización. La publicación requiere confirmar revisión de claridad, pertinencia pedagógica y distractores.
- Cada publicación selecciona explícitamente los alumnos autorizados. Este alcance utiliza permisos individuales mientras se desarrolla la relación por curso.
- Cada docente gestiona y prueba sus propias publicaciones. Los administradores pueden consultar todas.
- Los alumnos ven únicamente las actividades activas que les hayan asignado. Cada tarjeta muestra una imagen, nombre, descripción y acceso a la ejecución.
- Los archivos se guardan bajo `godotactividades/<identificador>/`, fuera de los estáticos públicos. `GODOT_ACTIVITIES_ROOT` define esa raíz. PostgreSQL conserva metadatos y autorizaciones.
- La ejecución se presenta en un iframe aislado del origen de la plataforma. Sus archivos usan enlaces firmados de dos horas y comprueban que la autorización siga vigente.
- La primera integración admite exportaciones Web de Godot 4 de un solo hilo, sin PWA, con `.html`, `.js`, `.wasm` y `.pck` coherentes. Límite del ZIP 150 MiB, descomprimido 300 MiB y 300 archivos. Portada PNG, JPEG o WebP de hasta 8 MiB, normalizada como PNG.

## Entrega de prueba

La carpeta proporcionada `godotactividades/reactor simulador` contiene `reactors.exe`, `reactors.console.exe` y `reactors.pck`. El paquete indica Godot 4.5. El usuario confirmó que dispone exclusivamente de esos archivos. Se combinó temporalmente su PCK con las plantillas Web de Godot 4.7.2 instalado por Steam. El motor cargó escenas, pero rechazó los scripts con el error `Binary GDScript is not compatible with this engine version`. La ejecución del reactor queda pendiente de una exportación Web compatible. La carga experimental se retiró después de la prueba.

Se creó y exportó una actividad técnica temporal con Godot de Steam para probar el flujo completo. Se verificaron la carga desde formulario, la previsualización, el botón del contador, la publicación y la tarjeta con portada desde la cuenta estudiantil. Las dos cargas de prueba y los archivos temporales se eliminaron al terminar.

Las 119 pruebas de cuentas y actividades pasaron el 2026-11-15 en PostgreSQL local con un esquema temporal aislado y eliminado al finalizar.

## Plan

1. Añadir modelos y migración de actividades con propietario y alumnos autorizados.
2. Implementar carga por formulario, validación del ZIP y de la portada, y almacenamiento transaccional con limpieza ante errores.
3. Conectar el inicio por rol con el catálogo, la gestión y la ejecución aislada.
4. Verificar autorizaciones, archivos malformados, rutas de ZIP, revocación de permisos y presentación en escritorio y móvil.

## Criterios de aceptación

- [x] Un docente puede publicar un paquete Web válido mediante el formulario con su portada y alumnos seleccionados.
- [x] Un alumno autorizado ve la tarjeta y puede abrir su actividad.
- [x] Un alumno ajeno, una cuenta sin rol y un visitante carecen de acceso a la publicación y sus archivos.
- [x] Un alumno carece de acceso al formulario de subida.
- [x] Los paquetes ejecutables, ZIP con rutas externas y exportaciones incompletas se rechazan con un mensaje comprensible.
- [x] El contenido de la actividad se ejecuta dentro de un iframe con sandbox y sin acceso al DOM de la plataforma.
- [x] La revocación de permisos impide nuevas solicitudes de archivos, incluso con un enlace firmado previo.
- [x] El catálogo se adapta a móvil y muestra un estado vacío cuando corresponde.

El registro de puntajes, la edición de actividades y las asignaciones por curso se desarrollarán en especificaciones posteriores.
