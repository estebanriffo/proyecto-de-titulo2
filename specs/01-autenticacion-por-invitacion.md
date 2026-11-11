# SPEC 01 — Autenticación y registro por invitación

> **Estado:** Aprobado
> **Depende de:** Ninguna spec previa
> **Fecha:** 2026-11-01
> **Objetivo:** Habilitar cuentas únicas por correo con registro por invitación, grupos de Django e inicio, cierre y recuperación de sesión.

## Alcance

**Incluye:**

- Inicialización del proyecto con estructura convencional de Django: `manage.py`, `config/`, `accounts/` y plantillas del servidor.
- Django, django-allauth, django-environ y PostgreSQL desde desarrollo.
- Usuario personalizado configurado antes de la primera migración.
- Acceso con correo y contraseña, sin nombre de usuario.
- Invitaciones enviadas por administradores y docentes a un correo determinado.
- Enlaces de un solo uso que vencen 48 horas después de su emisión.
- Reenvío que invalida el enlace anterior y reinicia el plazo de 48 horas.
- Registro y activación al aceptar la invitación y establecer una contraseña válida.
- Inicio y cierre de sesión mediante cookies y sesiones Django.
- Recuperación de contraseña por correo mediante allauth.
- Etiquetas de cuenta representadas por los grupos `estudiante`, `docente` y `administrador`.
- Asignación y retiro de grupos exclusivamente por administradores.
- Pantalla de espera para cuentas activas sin grupo.
- Pantalla mínima de acceso autorizado para usuarios con grupo.
- Administración inicial mediante `createsuperuser` y Django Admin.
- Envío de correo a consola en desarrollo y SMTP configurable en producción.
- Formularios y mensajes en español, con etiquetas accesibles y navegación por teclado.

**Fuera de alcance:**

- Registro público, autenticación social, JWT, API de autenticación y frontend separado.
- MFA, cambio autónomo de correo y correos secundarios.
- Etiquetas libres, cursos y asignación de estudiantes a docentes.
- Actividades educativas, seguimiento de aprendizaje, IA y paneles pedagógicos completos.
- Eliminación de cuentas, suscripciones y pagos.
- Despliegue AWS y contratación o configuración de un proveedor SMTP externo.

## Modelo de datos

### `accounts.User`

Extender `AbstractUser` y establecer `AUTH_USER_MODEL = 'accounts.User'` antes de ejecutar `migrate`.

| Campo | Definición |
| --- | --- |
| `id` | Clave primaria de Django |
| `username` | Eliminado del modelo de autenticación |
| `email` | `EmailField`, obligatorio y único |
| `password` | Hash administrado por Django; nunca texto plano |
| `is_active` | Cuenta habilitada; independiente de la asignación de grupos |
| `is_staff`, `is_superuser` | Indicadores internos de Django; no editables por docentes ni invitados |
| `groups`, `user_permissions` | Relaciones nativas de Django |
| `date_joined`, `last_login` | Fechas de auditoría nativas |

Usar `USERNAME_FIELD = 'email'` y un manager compatible con `create_user` y `create_superuser` sin username.

La clave de identidad es el correo con espacios exteriores eliminados y convertido a minúsculas.
Aplicar esa regla en formularios, manager, administración e integración con allauth.
No transformar puntos ni sufijos `+` de proveedores de correo.

La base de datos debe imponer unicidad insensible a mayúsculas con `UniqueConstraint(Lower('email'), name='accounts_user_email_ci_unique')`.
Agregar una restricción que rechace correos con espacios exteriores para impedir variantes por escrituras directas.
La validación de formularios no sustituye las restricciones de PostgreSQL.
Capturar conflictos de unicidad concurrentes y devolver errores controlados.

### `accounts.Invitation`

| Campo | Definición |
| --- | --- |
| `id` | Clave primaria |
| `email` | Correo normalizado del destinatario, único por registro de invitación |
| `token_digest` | Resumen SHA-256 de un token aleatorio criptográfico; único |
| `invited_by` | FK a `settings.AUTH_USER_MODEL`; conservar referencia con `SET_NULL` si se elimina al emisor |
| `created_at` | Fecha inicial en UTC |
| `sent_at` | Fecha de emisión del enlace vigente |
| `expires_at` | `sent_at` más 48 horas |
| `accepted_at` | Nulo hasta completar el registro |
| `accepted_user` | FK nullable a `settings.AUTH_USER_MODEL` |

No guardar el token original en la base de datos ni incluirlo en logs de producción.
Un reenvío reemplaza el resumen del token vigente.
Una invitación está disponible cuando no fue aceptada y la hora actual es estrictamente anterior a `expires_at`.
En el instante de vencimiento ya es inválida.
El estado pendiente, vencida o aceptada se deriva de esos datos.

No crear `User` al enviar la invitación.
Crearlo únicamente al aceptar mediante POST válido.
La cuenta nace activa, con correo verificado y sin grupos.
Esto también se aplica a invitaciones enviadas por administradores; la asignación del grupo es una acción administrativa separada.

### Modelos reutilizados

- `auth.Group` y `auth.Permission` representan roles y autorización.
- `allauth.account.EmailAddress` registra un único correo principal y verificado por cuenta.
- `django.contrib.sessions` mantiene las sesiones en PostgreSQL.
- Las migraciones de datos crean los tres grupos sin crear usuarios ni contraseñas.

## Comportamiento y autorización

### Invitación y aceptación

1. Un administrador o docente autenticado introduce el correo en `/accounts/invitations/`.
2. El servidor valida permisos y comprueba que no exista una cuenta con ese correo normalizado.
3. Si no existe, genera o renueva la invitación y envía el enlace al destinatario.
4. El destinatario abre `/accounts/invitations/accept/<token>/` y ve el correo como dato de solo lectura.
5. El GET no consume la invitación ni activa cuentas; los escáneres de correo no deben agotarla.
6. El destinatario establece y confirma su contraseña mediante POST protegido contra CSRF.
7. Una transacción bloquea la invitación y vuelve a comprobar vigencia, token y correo único.
8. La transacción crea la cuenta, registra el correo verificado y marca la invitación como aceptada.
9. Se redirige a iniciar sesión con confirmación de registro completado.
10. Tras identificarse, la persona sin grupo llega a `/accounts/pending/`.

Una segunda aceptación no crea usuarios ni altera contraseñas.
Una cuenta ya existente no recibe una nueva cuenta ni un nuevo enlace de alta.
El formulario indica al emisor autorizado que corresponde usar inicio de sesión o recuperación.

Ante un token inválido, vencido o consumido, mostrar un mensaje comprensible y la indicación de solicitar otra invitación al docente o administrador.
No mostrar el correo del destinatario cuando el token no sea válido.

La invitación no permite seleccionar grupos ni modificar el correo mediante campos ocultos o POST manipulado.
El endpoint público de registro de allauth debe permanecer cerrado salvo que el flujo interno haya validado una invitación.
No permitir saltarse la invitación accediendo directamente a `/accounts/signup/`.

### Matriz de acceso

| Actor | Invitar | Asignar grupos | Acceso después de autenticarse |
| --- | --- | --- | --- |
| Visitante | No | No | Inicio de sesión, aceptación y recuperación |
| Cuenta sin grupo | No | No | Espera y cierre de sesión; recuperación disponible |
| `estudiante` | No | No | Pantalla autorizada mínima |
| `docente` | Sí | No | Pantalla autorizada e invitaciones |
| `administrador` | Sí | Sí | Pantalla autorizada y gestión de cuentas |
| Superusuario | Sí | Sí | Django Admin y acceso de arranque |

Comprobar estos permisos en el servidor en cada solicitud.
Cambiar grupos debe surtir efecto en la siguiente solicitud, sin depender de datos guardados al iniciar sesión.
La pantalla de espera no es una cuenta inactiva: `is_active=False` bloquea el inicio de sesión.

Los grupos pueden combinarse utilizando la relación nativa de Django.
Solo la pertenencia efectiva a `docente` o `administrador`, o ser superusuario, permite invitar.
Ser `is_staff` por sí solo no concede ese permiso.
Configurar el acceso administrativo necesario para el grupo `administrador` sin convertirlo automáticamente en superusuario.
Las operaciones administrativas no permitirán a docentes modificar grupos, permisos ni indicadores internos.

### Sesión y recuperación

- Reutilizar los flujos de allauth para acceso por correo, logout y restablecimiento de contraseña.
- El logout se ejecuta por POST con CSRF y redirige al inicio de sesión.
- Validar destinos de redirección para evitar enlaces externos arbitrarios.
- La recuperación responde de forma genérica exista o no el correo.
- Usar tokens de recuperación del framework, de un solo uso efectivo tras cambiar la contraseña.
- Recuperar contraseña no asigna grupos, reactiva cuentas deshabilitadas ni crea cuentas.
- Aplicar los validadores de contraseña de Django y límites de intentos de allauth.
- No ofrecer persistencia voluntaria de sesión en esta primera interfaz; usar sesión de navegador.

## Archivos previstos

| Ruta | Responsabilidad |
| --- | --- |
| `manage.py` | Entrada estándar de Django |
| `requirements.txt` | Dependencias con versiones compatibles fijadas al implementar |
| `.gitignore`, `.env.example` | Exclusión de secretos y variables documentadas |
| `config/__init__.py`, `config/settings.py`, `config/urls.py` | Configuración, middleware y rutas |
| `config/asgi.py`, `config/wsgi.py` | Entradas del servidor |
| `accounts/apps.py`, `accounts/__init__.py` | Aplicación Django |
| `accounts/models.py`, `accounts/managers.py` | Usuario, invitaciones y creación de cuentas |
| `accounts/migrations/` | Esquema, restricciones y grupos iniciales |
| `accounts/admin.py` | Gestión restringida de cuentas y grupos |
| `accounts/adapters.py` | Puente con el registro y correo verificado de allauth |
| `accounts/forms.py`, `accounts/services.py` | Validación, emisión y aceptación atómica |
| `accounts/views.py`, `accounts/urls.py`, `accounts/access.py` | Vistas convencionales y comprobaciones de acceso |
| `templates/base.html` | Estructura accesible compartida |
| `templates/account/` | Personalización de pantallas y correos de allauth |
| `templates/accounts/` | Invitaciones, aceptación, espera y acceso autorizado |
| `accounts/tests/` | Pruebas funcionales y de concurrencia con PostgreSQL |
| `README.md` | Instalación, migraciones, administrador inicial y ejecución |

Mantener nombres convencionales y evitar capas o frameworks adicionales para esta funcionalidad.
El detalle de las versiones se fija al implementar tras comprobar compatibilidad; no se exige una versión numérica no validada en este spec.

## Configuración

Leer con django-environ: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` y `SITE_URL`.

`SITE_URL` define el origen confiable de los enlaces enviados y debe usar HTTPS en producción.
La configuración no debe depender del encabezado Host recibido para construir invitaciones.
Rechazar configuraciones SMTP con TLS y SSL simultáneos.
Las variables del proceso tienen prioridad sobre el archivo `.env` local.
No usar SQLite como sustituto silencioso de PostgreSQL.
La ausencia de secretos o conexión requerida produce un error de configuración claro.

La integración de allauth usa autenticación por correo, campos de alta sin username y unicidad de correo.
El adaptador reconoce exclusivamente el correo de una invitación válida como previamente verificado.
Mantener protección para cualquier otra vía de creación de cuenta.
No deshabilitar globalmente la verificación como atajo para implementar invitaciones.

En producción: `DEBUG=False`, cookies de sesión y CSRF seguras, cookies de sesión HttpOnly y configuración HTTPS apropiada.
El backend de consola se utiliza solamente en desarrollo.
Los tokens y contraseñas no deben aparecer en mensajes de error ni registros de producción.

## Plan de implementación

Cada paso incluye sus pruebas pertinentes y deja Django ejecutable al completarse.
Dividir cada paso en commits pequeños si supera aproximadamente 30–50 líneas de lógica.

1. Crear el proyecto, la aplicación `accounts`, el usuario personalizado mínimo y su manager antes de migrar. Agregar dependencias, configuración con django-environ y PostgreSQL. Verificar `python manage.py check`.
2. Crear las migraciones del usuario y sus restricciones. Ejecutar `python manage.py migrate` sobre PostgreSQL y verificar `createsuperuser` con correo.
3. Incorporar allauth, sus rutas, middleware y configuración por correo. Cerrar el registro público y habilitar login/logout del superusuario.
4. Crear los grupos mediante migración de datos y la administración restringida. Incorporar las pantallas autorizada y de espera con controles de servidor.
5. Agregar el modelo de invitación y su migración. Incorporar el formulario y servicio de envío por administradores y docentes, incluido el reenvío que rota el token.
6. Integrar la aceptación transaccional con allauth y el correo verificado. Cubrir vencimiento, token consumido, correo no editable y conflictos concurrentes.
7. Personalizar los flujos y plantillas de recuperación de contraseña, acceso y cierre de sesión. Verificar que una recuperación no modifique grupos ni habilitación.
8. Completar las plantillas accesibles, mensajes de error y manejo del fallo de correo. Un fallo de envío no debe mostrarse como éxito ni crear una cuenta; debe permitir reintentar con un enlace nuevo.
9. Completar `README.md` y `.env.example` con instalación, PostgreSQL, migraciones, `createsuperuser`, envío de invitaciones, asignación de grupos y SMTP. Actualizar la descripción del estado real de la aplicación en `AGENTS.md`.

El primer paso ejecutable es inicializar el esqueleto de Django con el usuario personalizado antes de aplicar migraciones.
El último entregable es una guía reproducible para registrar por invitación y habilitar el acceso mediante grupos.

## Criterios de aceptación

- [ ] `python manage.py check` pasa con la configuración de desarrollo documentada.
- [ ] Las migraciones se aplican a una base PostgreSQL vacía y crean los tres grupos.
- [ ] `createsuperuser` solicita correo y contraseña, sin username, y permite entrar a Django Admin.
- [ ] Acceder directamente al registro público no permite crear cuentas.
- [ ] Administrador y docente pueden enviar invitaciones; visitante, estudiante y cuenta sin grupo no pueden hacerlo mediante GET ni POST directo.
- [ ] Emitir una invitación no crea un usuario.
- [ ] Un enlace funciona antes de 48 horas y falla exactamente al cumplirlas o después.
- [ ] Reenviar invalida el enlace anterior y emite uno con 48 horas nuevas.
- [ ] Abrir el enlace por GET no lo consume.
- [ ] Aceptar por POST válido crea exactamente una cuenta activa y un correo principal verificado, sin grupos.
- [ ] El correo enviado por un POST manipulado no reemplaza el destinatario invitado.
- [ ] Un enlace usado no crea otra cuenta ni permite cambiar la contraseña existente.
- [ ] Dos aceptaciones concurrentes de la misma invitación producen una sola cuenta y respuestas controladas.
- [ ] `Persona@Colegio.cl`, `persona@colegio.cl` y ` persona@colegio.cl ` corresponden a una sola identidad.
- [ ] La base de datos rechaza duplicados insensibles a mayúsculas y correos con espacios exteriores incluso al omitir formularios.
- [ ] Invitaciones concurrentes para el mismo correo no dejan dos enlaces utilizables.
- [ ] Los flujos de administración y allauth no permiten asociar el mismo correo normalizado a cuentas distintas.
- [ ] Correo válido y contraseña correcta permiten iniciar sesión; errores de credenciales no revelan cuál dato falló.
- [ ] Una cuenta sin grupo solo accede a espera, cierre de sesión y flujos necesarios de recuperación.
- [ ] Asignar un grupo permite el acceso correspondiente en la siguiente solicitud; retirarlos devuelve a espera.
- [ ] Un docente no puede asignarse grupos ni modificar permisos o indicadores internos mediante solicitudes manipuladas.
- [ ] El logout requiere POST con CSRF y la sesión cerrada no accede a vistas protegidas.
- [ ] La recuperación envía un enlace utilizable al correo de una cuenta habilitada y permite entrar con la contraseña nueva.
- [ ] La respuesta pública de recuperación no revela si existe una cuenta.
- [ ] El restablecimiento no concede grupos y su enlace deja de servir después del cambio de contraseña.
- [ ] Los formularios rechazan peticiones sin CSRF y no redirigen a dominios externos mediante `next`.
- [ ] El fallo de SMTP informa del envío fallido al emisor autorizado sin crear usuarios.
- [ ] Las pantallas se operan por teclado y los campos y errores tienen etiquetas accesibles.
- [ ] `.env` está excluido y `.env.example` no contiene secretos reales.
- [ ] Las pruebas automatizadas usan PostgreSQL e incluyen pruebas transaccionales para las carreras de aceptación y unicidad.
- [ ] `python manage.py test accounts` pasa y el README permite reproducir el flujo completo.

## Decisiones tomadas y descartadas

- **Sí: registro por invitación.** Mantiene el alta controlada y evita el registro público directo de menores.
- **Sí: administradores y docentes invitan.** Decisión expresa del usuario.
- **Sí: grupos asignados únicamente por administrador.** El docente puede invitar, pero no autorizar el acceso pedagógico.
- **Sí: cuenta activa sin grupo y pantalla de espera.** Separa autenticación de autorización.
- **Sí: enlaces de 48 horas, de un uso y renovables.** Limita la vigencia y permite corregir envíos fallidos.
- **Sí: correo como identificador único normalizado.** Evita múltiples cuentas por diferencias de mayúsculas o espacios exteriores.
- **Sí: restricciones en PostgreSQL.** La comprobación previa en Python no evita carreras concurrentes.
- **Sí: Django convencional con plantillas y sesiones.** Confirmado por el usuario para este primer flujo.
- **Sí: allauth y django-environ.** Requisitos expresos para autenticación y configuración.
- **No: verificación adicional después de aceptar.** El enlace enviado al mismo correo proporciona la prueba de posesión acordada.
- **No: alta automática con grupo estudiante.** El usuario eligió asignación posterior por administrador.
- **No: tokens JWT, autenticación social o etiquetas libres.** No forman parte del alcance aprobado para definición.
- **No: inferir grupos a partir del correo o de campos enviados por el invitado.** Evita concesión de privilegios no autorizada.

## Riesgos identificados

| Riesgo | Mitigación |
| --- | --- |
| Robo o reenvío de una invitación | Token criptográfico, 48 horas, un uso, HTTPS y ocultación en logs |
| Solicitudes simultáneas | Transacciones, bloqueo de invitación y restricciones de unicidad |
| Ruta alternativa de registro | Cerrar alta pública y probar los endpoints directos de allauth |
| Escalada de permisos desde Django Admin | Restringir formularios y permisos de administración; no otorgar administración a docentes |
| Confundir cuenta activa con acceso aprobado | Comprobar grupos en cada solicitud y mantener espera separada |
| Pérdida o fallo de correo | Error explícito y reenvío con rotación del token |
| Uso de correos personales de menores | Registrar solamente el correo acordado institucionalmente; no pedir diagnósticos ni datos adicionales |
| Diferencias entre versiones de dependencias | Fijar versiones compatibles y validar los hooks utilizados contra su documentación |

## Referencias técnicas

- [Django: restricciones de modelos](https://docs.djangoproject.com/en/5.2/ref/models/constraints/) para la unicidad funcional en PostgreSQL.
- [django-allauth: configuración de cuentas](https://docs.allauth.org/en/latest/account/configuration.html) para acceso por correo, unicidad y configuración de registro.
- [django-allauth: uso avanzado](https://docs.allauth.org/en/latest/account/advanced.html) para adaptar el registro por invitación y reconocer un correo ya verificado.
- [django-environ: inicio rápido](https://django-environ.readthedocs.io/en/stable/quickstart.html) para variables de entorno y `DATABASE_URL`.

## Qué no incluye esta spec

No se implementan actividades, IA, cursos, seguimiento, pagos, eliminación de cuentas, autenticación social ni despliegue cloud.
La pantalla autorizada es un destino mínimo de autenticación y no un panel pedagógico completo.
Esta spec fue aprobada por el usuario; no contiene una implementación ni acredita verificaciones ejecutadas.
