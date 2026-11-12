# Aprendo a mi Ritmo

## Desarrollo de la SPEC 01

El proyecto incluye el usuario personalizado con correo, la configuración mediante
django-environ y la migración inicial con restricciones de unicidad y espacios.
Los pasos 1 a 6 están verificados con las migraciones aplicadas en PostgreSQL local
y 90 pruebas correctas. Incluyen allauth, acceso por correo, verificación de correo,
cierre de sesión mediante POST, registro público cerrado, grupos, envío y reenvío
de invitaciones y aceptación transaccional. El paso 7 incorpora la recuperación
de contraseña con pantallas y correo en español, enlace basado en `SITE_URL`,
respuesta pública genérica y manejo de errores de envío. Pasaron 13 pruebas sin
base de datos y se renderizaron los cinco estados de sus plantillas. La suite
ampliada contiene 104 pruebas y su ejecución con PostgreSQL sigue pendiente para
verificar este incremento.

### Preparar el entorno en Windows

Se verificó este incremento con Python 3.14.4 y Django 5.2.19.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Guardar la clave generada en `SECRET_KEY` de `.env`. Completar `DATABASE_URL`
con el usuario, contraseña, host y nombre de una base PostgreSQL de desarrollo.
El marcador `CAMBIAR_CONTRASENA` debe sustituirse por la contraseña del rol de
PostgreSQL indicado en la URL. La base y el rol deben existir en el servidor.
Las variables del proceso tienen prioridad sobre `.env`.

### Crear el esquema y el administrador

Con PostgreSQL disponible y las credenciales configuradas, ejecutar en este orden.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

`createsuperuser` solicita el correo y la contraseña del administrador.

### Abrir la pantalla de acceso

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir `http://localhost:8000/accounts/login/` e ingresar con el correo y la
contraseña del superusuario. En el primer acceso, allauth solicita verificar el
correo. Durante el desarrollo, el mensaje y su enlace aparecen en la consola del
servidor. Abrir el enlace, confirmar el correo y volver a iniciar sesión para
acceder a Django Admin.

Los enlaces de verificación usan el origen definido en `SITE_URL`. El cierre de
sesión requiere un formulario POST.

### Probar los roles en desarrollo

Con las migraciones aplicadas y `DEBUG=True`, ejecutar este comando en otra terminal.

```powershell
.\.venv\Scripts\python.exe manage.py create_demo_users
```

El comando solicita una contraseña y su confirmación sin mostrarlas en pantalla.
La contraseña se usa para las cuentas ficticias nuevas de la siguiente tabla.

| Correo ficticio | Grupo | Destino al iniciar sesión |
| --- | --- | --- |
| `estudiante@aprendo.example` | estudiante | Inicio con «Actividades» y «Mi progreso» bajo «Próximamente» |
| `docente@aprendo.example` | docente | Inicio con «Enviar invitaciones» y módulos docentes bajo «Próximamente» |
| `administrador@aprendo.example` | administrador | Acceso habilitado y enlace a gestión de cuentas |
| `pendiente@aprendo.example` | Sin grupo | Pantalla de espera |

Estas cuentas de desarrollo tienen su correo marcado como verificado. Repetir el
comando crea las cuentas faltantes y conserva las cuentas existentes. El comando
requiere `DEBUG=True`.

Cerrar la sesión del superusuario antes de probar cada cuenta en
`http://localhost:8000/accounts/login/`. El superusuario llega a Django Admin.
En el inicio de estudiante, «Actividades» y «Mi progreso» aparecen como texto.
Abrir `/accounts/invitations/` directamente con esa cuenta devuelve HTTP 403.
Con la cuenta docente, «Enviar invitaciones» abre el formulario y «Gestionar
actividades» y «Revisar progreso de estudiantes» aparecen bajo «Próximamente».

### Asignar y retirar roles

Desde Django Admin, abrir **Cuentas → Usuarios**, seleccionar una cuenta y editar
sus grupos. También puede hacerlo una cuenta del grupo `administrador` mediante
**Gestionar cuentas y asignar roles**. Ese grupo recibe los permisos de consulta
y modificación de usuarios al aplicar las migraciones.

La gestión permite cambiar grupos y habilitación, con el correo como identidad
de solo lectura. Los tres grupos disponibles son `estudiante`, `docente` y
`administrador`. Seleccionar un solo rol educativo por cuenta. Si una cuenta ya
tiene ambos, su inicio pide contactar a un administrador para corregir la
asignación. Al aceptar una invitación se crea una cuenta
activa, con su correo verificado y sin grupos. Después un administrador le asigna
los roles correspondientes.

Para comprobar el cambio con una sesión abierta, iniciar sesión con la cuenta
pendiente en otro navegador, asignarle un grupo desde la administración y pulsar
**Comprobar mi acceso**. Retirar todos los grupos devuelve a espera en la siguiente
solicitud. Desactivar la cuenta bloquea su acceso. La gestión de roles exige
pertenecer al grupo `administrador` o ser superusuario.

### Enviar y reenviar invitaciones

Iniciar sesión como docente, administrador o superusuario y abrir
`http://localhost:8000/accounts/invitations/`. Docentes y administradores también
pueden abrir **Enviar invitaciones** desde su pantalla de acceso habilitado.
Desde Django Admin, **Ver el sitio** abre esa pantalla con el mismo enlace.

Ingresar un correo ficticio para las pruebas y pulsar **Enviar o reenviar
invitación**. En desarrollo con el backend de consola, el mensaje aparece en la
terminal del servidor. Los enlaces usan `SITE_URL` como origen.

Cada correo tiene un único registro de invitación. Un reenvío sustituye el resumen
SHA-256 del token y renueva las 48 horas de vigencia. La operación comprueba los
roles en el servidor y bloquea el registro durante la renovación. Un error de
envío revierte la emisión o renovación e informa al emisor para que reintente.

### Revisar el correo y aceptar una invitación

La consola del servidor es la terminal donde está ejecutándose `manage.py runserver`.
Puede usarse la terminal integrada de Codex o **Terminal → Nueva terminal** en
VS Code, desde la carpeta del proyecto. Mantener esa terminal abierta mientras se
usa la página.

Con el backend de consola, al enviar una invitación aparece allí un mensaje cuyo
asunto es **Invitación a Aprendo a mi Ritmo**. Copiar el enlace completo que contiene
`/accounts/invitations/accept/` y abrirlo en el navegador. En producción con SMTP,
el destinatario recibe ese enlace en su correo.

La página muestra el correo invitado como dato de solo lectura y solicita una
contraseña y su confirmación. Pulsar **Crear mi cuenta** completa el registro y
redirige al inicio de sesión. La cuenta queda activa, con un único correo principal
verificado y sin grupos. Después de iniciar sesión llega a la pantalla de espera
hasta que un administrador le asigne un rol.

Abrir el enlace permite revisar la invitación sin consumirla. La creación se
ejecuta mediante POST con CSRF dentro de una transacción que bloquea y comprueba
otra vez la invitación. Los enlaces inválidos, vencidos, usados o reemplazados por
un reenvío muestran una página de invitación no disponible. Un conflicto de correo
revierte el alta completa.

La aceptación usa `Referrer-Policy: strict-origin` para enviar el origen del
formulario y limitar el Referer al origen. Después de actualizar desde la política
anterior, volver a abrir el enlace original antes de completar el formulario.

Los manejadores de registro de Django ocultan los tokens de invitación en sus
mensajes, incluidos los de solicitudes, servidor y rechazo CSRF. Al definir la
infraestructura de producción, configurar también
la ocultación de esos enlaces en los registros del proxy y del servidor HTTP.

### Recuperar la contraseña

Abrir `http://localhost:8000/accounts/login/` y pulsar **¿Olvidaste tu contraseña?**.
También puede abrirse directamente `http://localhost:8000/accounts/password/reset/`.
Ingresar el correo de una cuenta habilitada y pulsar **Enviar enlace de recuperación**.

La confirmación muestra el mismo mensaje para cuentas habilitadas, deshabilitadas
y correos sin cuenta. Los mensajes de recuperación se envían a cuentas habilitadas.
En desarrollo, buscar **Recuperación de contraseña** en la terminal donde se ejecuta
`manage.py runserver`, copiar el enlace completo y abrirlo en el navegador. Con SMTP
configurado, el mensaje llega al destinatario por correo.

Allauth sustituye el token de la dirección por `set-password` antes de mostrar el
formulario. Elegir una contraseña, repetirla y pulsar **Guardar nueva contraseña**.
Al completar el cambio, pulsar **Iniciar sesión** y usar la nueva contraseña.
El acceso posterior se rige por los roles asignados y la habilitación de la cuenta.

El enlace usa los tokens del framework y el plazo de `PASSWORD_RESET_TIMEOUT` de
Django. Tras cambiar la contraseña, ese enlace pierde su validez. Una página de
enlace inválido, vencido o utilizado permite solicitar otro. Los formularios usan
CSRF y los límites de intentos de allauth. Ante un fallo de envío, el formulario
muestra un error para reintentar. Los enlaces del correo usan el origen `SITE_URL`.

### Comprobar este incremento

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test accounts
```

Las pruebas del manager verifican normalización del correo, hash de contraseña e
indicadores en memoria. Las pruebas de base de datos comprueban escrituras directas,
correos duplicados con distintas mayúsculas, espacios exteriores, creaciones
concurrentes y el comando `createsuperuser`. Django crea una base PostgreSQL de
pruebas independiente y la elimina al finalizar. El rol configurado necesita
permiso para crear esa base de pruebas.

La suite cubre además login, verificación de correo, límites de intentos, CSRF,
logout, cierre del registro público, destinos según rol, asignación y retiro de
grupos con sesión abierta, acceso administrativo, peticiones manipuladas y el
comando de cuentas ficticias.

Las pruebas de invitación cubren permisos, correos existentes, rotación de tokens,
vencimiento exacto, CSRF, origen confiable del enlace, fallos de correo,
restricciones de PostgreSQL, emisiones y reenvíos concurrentes, aceptación de un
solo uso, correo y roles manipulados, login posterior, reversión del alta ante
conflictos y aceptaciones concurrentes. La aceptación con CSRF activo se verifica
con orígenes de localhost, 127.0.0.1 y HTTPS, además del rechazo de orígenes nulos
y ajenos con token CSRF válido. También comprueban la ocultación del token
en los mensajes de los registros de Django. Las 90 pruebas anteriores al paso 7
pasaron con PostgreSQL. Las nuevas pruebas de recuperación verifican el cambio y
login posterior, roles, cuentas deshabilitadas, cuentas sin grupo, enlace usado o
vencido, CSRF, límites de solicitudes, origen del enlace y fallos de envío. Su
ejecución con PostgreSQL sigue pendiente porque se rechazó el permiso para ejecutar
la suite. Para ejecutar las comprobaciones que usan exclusivamente memoria,
puede usarse el siguiente comando.

```powershell
.\.venv\Scripts\python.exe manage.py test accounts.tests.test_managers accounts.tests.test_invitations.InvitationValidationTests accounts.tests.test_invitation_acceptance.InvitationLoggingTests accounts.tests.test_password_reset.PasswordResetLoggingTests
```

### Configuración

`SECRET_KEY` y `DATABASE_URL` son obligatorias. `DATABASE_URL` debe indicar
PostgreSQL. En producción también se requieren `ALLOWED_HOSTS` y `SITE_URL`
con HTTPS. Las sesiones terminan al cerrar el navegador y las cookies usan HTTPS
cuando `DEBUG=False`.

El correo usa consola durante el desarrollo. Las variables SMTP están documentadas
en `.env.example`. La configuración rechaza TLS y SSL simultáneos.

El informe y los diagramas están excluidos mediante `.gitignore`.
