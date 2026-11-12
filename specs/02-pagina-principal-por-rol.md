# SPEC 02 — Página principal por rol

> **Estado:** Borrador
>
> **Depende de:** SPEC 01 — Autenticación y registro por invitación
>
> **Fecha:** 2026-11-12
>
> **Objetivo:** Mostrar a estudiantes y docentes un inicio con las funciones de su rol y validar en el servidor el acceso a cada página protegida.

## Alcance

**Incluye**

- Convertir `/accounts/home/` en el inicio autenticado por rol. El acceso desde `/` y el destino habitual después de iniciar sesión se resuelven con el flujo de la SPEC 01.
- Mostrar los enlaces operativos que la cuenta puede usar y las funciones futuras previstas para su rol como elementos sin enlace, con el texto visible «Próximamente».
- Impedir la asignación simultánea de los grupos `estudiante` y `docente` a una cuenta. Si existe una asignación anterior incompatible, bloquear las funciones de ambos perfiles y pedir que un administrador la corrija.
- Aplicar los permisos vigentes tanto al mostrar enlaces como al procesar solicitudes directas a sus destinos, incluidas las que modifican datos.

**Fuera de alcance**

- Desarrollo de actividades, progreso, tutorial, asistente de IA y preferencias de accesibilidad. Las guías U1 y U2 describen esas funciones como parte del producto. Esta spec toma de ellas las funciones previstas por perfil.
- Implementación de cursos y sus relaciones con estudiantes, docentes y actividades. Los módulos que consulten o modifiquen datos de un curso deberán comprobar también el permiso sobre ese recurso.

## Modelo de datos

Se reutilizan `accounts.User`, `User.groups` y los grupos de Django `estudiante`, `docente` y `administrador` de la SPEC 01. `docente` es el identificador interno del rol de profesor.

El inicio consulta los grupos de la cuenta para cada solicitud. El rol educativo válido puede ser `estudiante`, `docente` o ninguno. Los dos grupos educativos juntos representan un conflicto. La facultad de administración sigue sujeta a `can_manage_accounts`.

## Comportamiento y autorización

| Función del inicio | Estudiante | Docente | Administrador |
| --- | --- | --- | --- |
| Enviar invitaciones | Oculta | Disponible | Disponible |
| Gestionar cuentas y asignar roles | Oculta | Oculta | Disponible |
| Actividades | Próximamente | Oculta | Oculta |
| Mi progreso | Próximamente | Oculta | Oculta |
| Gestionar actividades | Oculta | Próximamente | Oculta |
| Revisar progreso de estudiantes | Oculta | Próximamente | Oculta |

La tabla describe cuentas con un solo grupo. Si una cuenta tiene el grupo `administrador`, conserva los accesos propios de ese grupo. El superusuario conserva Django Admin como destino predeterminado. Cerrar sesión sigue disponible para toda sesión autenticada.

- Las cuentas verificadas sin un grupo reconocido llegan a `/accounts/pending/`. Los visitantes pasan por inicio de sesión y las cuentas sin correo verificado siguen el flujo de verificación de allauth.
- Las invitaciones reutilizan `can_invite` en el inicio y en la vista. Django Admin comprueba el acceso con `can_manage_accounts` y sus permisos de consulta y cambio sobre cuentas.
- Una cuenta autenticada y verificada sin el permiso requerido recibe HTTP 403 al solicitar directamente una ruta operativa protegida. Las funciones marcadas «Próximamente» se presentan como texto, sin controles interactivos ni rutas asociadas.
- Una cuenta con ambos grupos educativos ve un mensaje que le indica contactar a un administrador. Su asignación queda disponible para revisión en Django Admin y puede corregirse seleccionando un solo rol educativo. Las facultades administrativas provienen del grupo correspondiente o del superusuario.
- Los cambios de grupos se reflejan en el inicio y en los destinos protegidos en la siguiente solicitud, con la sesión abierta. Las respuestas del inicio autenticado conservan `Cache-Control: no-store`.

## Plan de implementación

1. En `accounts/access.py`, definir la detección del rol educativo y del conflicto a partir de los grupos vigentes. Usarla en la autorización docente de `can_invite` y pasar el estado al inicio desde `accounts/views.py`.
2. En `accounts/admin.py`, validar la asignación de roles antes de guardar. Rechazar con un error de formulario una selección que incluya ambos grupos educativos y conservar la asignación anterior. Guardar el cambio dentro de una transacción que bloquee la cuenta hasta terminar la actualización de sus grupos. Permitir que un administrador corrija una cuenta en conflicto o cambie el rol educativo en un solo guardado.
3. Actualizar `templates/accounts/authorized.html` para mostrar las funciones de la matriz según el perfil y el mensaje de asignación incompatible cuando corresponda. Mantener navegación por teclado, foco visible y texto legible para los módulos «Próximamente».
4. Ampliar las comprobaciones en `accounts/tests/test_access.py` y `accounts/tests/test_invitations.py` para cubrir la matriz de acceso, el cambio de rol en sesión y la corrección de asignaciones incompatibles. Actualizar en `README.md` el recorrido de verificación con las cuentas ficticias.

## Criterios de aceptación

- [ ] Una cuenta con solo el grupo `estudiante` ve «Actividades» y «Mi progreso» como funciones próximas y solo los accesos operativos de su perfil. Solicitar invitaciones por GET o POST y abrir gestión de cuentas devuelve HTTP 403.
- [ ] Una cuenta con solo el grupo `docente` ve «Enviar invitaciones» como enlace operativo y los módulos de gestión de actividades y seguimiento como funciones próximas. Puede abrir y enviar el formulario de invitación. El acceso directo a gestión de cuentas devuelve HTTP 403.
- [ ] Un administrador puede abrir invitaciones y gestionar cuentas. Un superusuario inicia en Django Admin. Una cuenta sin grupo reconocido llega a la pantalla de espera.
- [ ] Un visitante que abre el inicio protegido pasa por el inicio de sesión. Una cuenta sin correo verificado pasa por verificación y una cuenta desactivada pierde el acceso aunque tuviera una sesión abierta.
- [ ] El formulario de roles rechaza guardar `estudiante` y `docente` simultáneamente, deja intacta la asignación anterior y permite cambiar de uno a otro en un guardado.
- [ ] Dos guardados concurrentes desde la administración que asignan roles educativos distintos dejan a la cuenta con un solo rol educativo.
- [ ] Una cuenta con una asignación anterior incompatible ve el mensaje de contacto y carece de acceso a invitaciones por el grupo docente. Corregir sus grupos actualiza sus accesos en la siguiente solicitud.
- [ ] Retirar el grupo `docente` durante una sesión quita el enlace de invitaciones y revoca la autorización para GET y POST en la siguiente solicitud si la cuenta carece de facultades administrativas.
- [ ] Con teclado se puede llegar a cada enlace disponible y ver el foco. Las funciones próximas se leen con su estado y quedan fuera del orden de tabulación.
- [ ] `python manage.py test accounts` pasa con PostgreSQL de desarrollo.

## Decisiones y riesgos

- **Inicio compartido por ruta.** Reutilizar `accounts:authorized` mantiene el destino configurado en allauth y concentra la navegación por rol en la plantilla existente.
- **Exclusión de roles educativos.** Una cuenta puede representar a un estudiante o a un docente. La validación se aplica al guardar desde la administración y el control de acceso detecta asignaciones antiguas incompatibles. La corrección manual evita adivinar el rol que corresponde.
- **Módulos previstos a la vista.** Mostrar «Próximamente» permite reconocer las futuras funciones de cada perfil sin exponer destinos que aún carecen de implementación.
- **Cambios de permiso durante una sesión.** Consultar los grupos en el servidor en cada solicitud evita que un enlace previamente visible conserve el acceso después de retirar el rol.
