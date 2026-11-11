# Instrucciones para trabajar en Aprendo a mi Ritmo

## Propósito y fuente

Este repositorio corresponde al proyecto de título **Aprendo a mi Ritmo**, asignatura Proyecto de Título TIHI84. La solución busca reducir el trabajo manual de adaptación de material del equipo del Programa de Integración Escolar (PIE) del Colegio Mary Ward de San Ignacio, Región de Ñuble, y favorecer la autonomía de estudiantes neurodivergentes.

Estas instrucciones se derivan del documento `C:\Users\esteb\Downloads\TIHI84_U1_Plantilla_informe_Guía_ABPro (3) (1).docx`. El documento contiene una propuesta académica; no demuestra que los componentes descritos estén implementados ni que las metas se hayan alcanzado.

- Equipo: Cristóbal Iturriaga, frontend; Esteban Riffo, backend.
- Académico guía: Christopher Alexander Muñoz Parra.
- Contraparte de validación pedagógica: equipo PIE del Colegio Mary Ward.
- Comunicarse y mantener la documentación del proyecto en español.

## Alcance del producto

Desarrollar una plataforma web responsiva con un entorno simplificado para estudiantes y paneles de gestión para docentes y administradores.

- Entregar inicialmente tres actividades interactivas de matemáticas, validadas por profesionales del área educativa.
- Permitir buscar y filtrar actividades por categorías y restringir su visibilidad según curso y permisos.
- Incorporar personalización transversal de tipografía, tamaño de texto, colores, contraste, volumen y síntesis de voz.
- Incluir un tutorial inicial y mantenerlo consistente con las funcionalidades disponibles.
- Ofrecer un asistente educativo de IA para orientar a estudiantes y apoyar a docentes en la adaptación de contenidos.
- Registrar progreso de usuarios autenticados: actividades realizadas, resultados y tiempos de sesión, sujeto a la definición de privacidad e identidad.
- Permitir el acceso público a tres actividades fijas sin guardar progreso, respuestas ni tiempos de sesión de visitantes.
- Incluir un formulario de soporte con clasificación del mensaje, confirmación de envío y recepción institucional.

El sistema es de apoyo pedagógico. No debe procesar, almacenar ni generar diagnósticos médicos o psicológicos. La creación de actividades posteriores al conjunto inicial corresponde a la institución, apoyada por las herramientas de la plataforma.

## Arquitectura prevista

Respetar la arquitectura cliente-servidor de **N-capas** seleccionada en el informe. Mantener separadas presentación, lógica de negocio y persistencia.

- **Presentación:** interfaz web accesible y actividades de Godot Engine exportadas para web mediante HTML5/WebAssembly. El cliente consume la API y nunca accede directamente a la base de datos.
- **Lógica de negocio:** Python con Django REST Framework para autenticación, autorización, actividades, progreso, soporte e integración de IA. Validar permisos y resultados en el servidor.
- **Persistencia:** PostgreSQL en red privada, sin exposición pública directa.
- **Infraestructura prevista:** AWS, almacenamiento de recursos en S3, distribución mediante CDN, WAF perimetral y gestión de secretos mediante un Vault o servicio equivalente cuya elección se documente.

No introducir microservicios ni una arquitectura basada en eventos como reemplazo de N-capas sin justificar y documentar el cambio. El informe no fija un framework de frontend, proveedor de IA, versiones de dependencias ni herramienta de infraestructura como código; revisar el repositorio y definirlos cuando sea necesario, sin presentarlos como decisiones ya aprobadas.

## Reglas funcionales

### Identidad y permisos

- Contemplar roles de estudiante, docente y administrador; aplicar autorización en el backend y aislamiento por curso.
- Implementar verificación de correo, recuperación de contraseña y confirmación por correo para eliminar una cuenta.
- Minimizar los datos personales y usar identidades institucionales conforme al modelo que se acuerde con la contraparte.
- Tratar la eliminación de cuenta y de sus datos como un flujo distinto de la desactivación de actividades.

### Gestión de actividades

- Permitir crear, consultar, modificar y desactivar actividades según el rol autorizado.
- Conservar el identificador al modificar una actividad. La eliminación funcional de una actividad cambia su estado a inactivo.
- Las actividades de docentes solo deben ser accesibles para sus estudiantes autorizados.
- Exigir revisión humana con una rúbrica que evalúe claridad, pertinencia pedagógica y distractores antes de publicar actividades, incluidas las adaptadas por IA.
- Validar tipo, contenido, tamaño y permisos de archivos cargados. No aceptar ejecutables ni HTML arbitrario como material de usuario.
- Separar los paquetes web de Godot publicados mediante un proceso controlado de las cargas de archivos realizadas por usuarios.

### Asistente de IA

- Mantener un rol de tutor: explicar instrucciones y ofrecer orientación sin resolver las actividades por el estudiante.
- Limitar las respuestas al contexto educativo y a las funciones de la plataforma; usar lenguaje claro y evitar sobreestimulación.
- Aplicar instrucciones de sistema y controles adicionales para reducir respuestas fuera de contexto, alucinaciones e instrucciones maliciosas presentes en archivos o mensajes.
- Mantener las claves del proveedor en el servidor. Evitar enviar información personal o sensible de estudiantes al modelo.
- El contenido generado o adaptado permanece pendiente de revisión humana hasta ser aprobado.
- No afirmar que los prompts por sí solos garantizan la seguridad o eliminan las alucinaciones.

## Accesibilidad y experiencia

- Tomar como objetivo WCAG 2.1 nivel AA y las directrices de accesibilidad de SENADIS mencionadas en el informe.
- Ofrecer tipografía y tamaño ajustables, alto contraste, lectura de instrucciones mediante text-to-speech y controles para desactivar animaciones y sonidos de fondo.
- Usar como mínimo un contraste de 4,5:1 para texto normal; verificar los criterios aplicables a cada componente.
- Mantener navegación por teclado, foco visible, etiquetas comprensibles y controles accesibles.
- Persistir las preferencias durante la sesión autenticada y ofrecer una opción para restablecerlas.
- Evitar distractores, sonidos inesperados, animaciones excesivas e interfaces que dependan exclusivamente del color.
- Optimizar para dispositivos de gama media-baja y conexiones inestables; evitar bloquear la interfaz durante la carga de recursos WASM.
- Auditar el DOM y validar por separado las actividades Canvas/WASM mediante pruebas de usabilidad con la contraparte. Un puntaje automático no acredita por sí solo conformidad con WCAG.

## Seguridad y privacidad

- Aplicar validación de entradas, autorización por recurso, cifrado en tránsito y protección de datos en reposo.
- Mantener secretos fuera del código fuente, archivos públicos y registros. Documentar variables de entorno sin incluir valores reales.
- Usar datos ficticios o anonimizados para desarrollo y pruebas; no incorporar datos reales de menores ni diagnósticos al repositorio.
- Mantener la base de datos en una red privada y exponer únicamente los servicios necesarios.
- Evitar registrar contenido sensible en logs, telemetría y mensajes de error. Revisar también los registros automáticos de infraestructura para el modo visitante.
- Incorporar alertas de fallos, consumo y eventos de seguridad pertinentes.
- El informe menciona las leyes 19.628, 21.459, 21.663 y 21.545, además del Decreto 83 y otras normas educativas. Verificar vigencia y aplicabilidad en fuentes oficiales antes de tomar decisiones normativas o afirmar cumplimiento.

## Metas de calidad del informe

Estas cifras son objetivos de validación, no resultados comprobados:

| Atributo | Objetivo | Validación prevista |
| --- | --- | --- |
| Carga inicial | FCP menor o igual a 3 segundos | Medición con condiciones de red y dispositivo documentadas |
| Disponibilidad | 99 % mensual en producción | Monitoreo del servicio |
| Concurrencia | Al menos 100 usuarios simultáneos sin degradación relevante | Pruebas de carga con umbrales definidos |
| Recuperación | RTO máximo de 25 minutos | Ensayo de recuperación y registro de tiempos |
| Accesibilidad del DOM | Objetivo de al menos 80/100 en auditoría automatizada, según el informe | Usar una herramienta que produzca ese puntaje y complementar con revisión manual |
| Autonomía | 90 % de usuarios realizan actividades sin asistencia | Pruebas de usabilidad con criterios y muestra documentados |

El informe cita ISO/IEC 25010 como referencia de calidad. No declarar certificación ni cumplimiento integral sin evidencia.

## Forma de trabajo

- Antes de modificar código, revisar la estructura real, las instrucciones locales y las dependencias existentes. No inventar comandos de ejecución ni asumir servicios instalados.
- Los pasos 1 a 6 de la SPEC 01 se verificaron en PostgreSQL local con 90 pruebas correctas. Incluyen usuario personalizado, restricciones, allauth, verificación de correo, acceso por correo, cierre de sesión POST, registro público cerrado, grupos iniciales, administración restringida, pantallas autorizada y de espera, envío y reenvío de invitaciones y aceptación transaccional. La migración `accounts.0003_invitation` está aplicada. El paso 6 crea la cuenta activa, su correo principal verificado mediante el adaptador de allauth y ningún grupo. Los GET de aceptación conservan la invitación y los POST comprueban CSRF, vigencia, token y unicidad bajo bloqueo. La aceptación usa `Referrer-Policy: strict-origin`, verificada en el servidor local, y tiene pruebas con CSRF activo para localhost, 127.0.0.1 y HTTPS. Se corrigió `no-referrer`, que provocaba `Origin: null` en los formularios del navegador. La suite cubre emisiones, reenvíos, aceptaciones y conflictos de correo concurrentes. Los manejadores de registro de Django tienen un filtro para ocultar tokens en enlaces de invitación y recuperación; los registros de infraestructura requerirán configuración al desplegar. El comando `create_demo_users` prepara cuentas ficticias verificadas con `DEBUG=True`.
- El paso 7 incorpora recuperación de contraseña con allauth, pantallas y correo en español, enlace con `SITE_URL`, confirmación pública genérica, correo a cuentas habilitadas y manejo de errores de envío. El formulario se revisó en el servidor local, se renderizaron cinco estados de plantillas y pasaron 13 pruebas sin base de datos. La suite ampliada contiene 104 pruebas. Sigue pendiente su ejecución con PostgreSQL porque se rechazó el permiso para ejecutarla. También quedan los pasos 8 y 9 del plan para la revisión completa de accesibilidad, errores y documentación final.
- Trabajar en incrementos pequeños, con criterios de aceptación trazables a los requerimientos y, cuando aporte claridad, expresados como Dado–Cuando–Entonces.
- El informe propone Scrum y prácticas de Extreme Programming, con sprints de dos a tres semanas y validación periódica con el equipo PIE.
- Documentar decisiones de arquitectura y cambios de alcance. No convertir propuestas o estimaciones académicas en hechos comprobados.
- Para cambios funcionales, ejecutar las comprobaciones pertinentes: permisos y aislamiento de datos, reglas de negocio, accesibilidad y manejo de errores. Evaluar carga, recuperación y seguridad cuando el cambio afecte esas propiedades.
- Antes de desplegar, verificar los controles de seguridad y accesibilidad relevantes y registrar los resultados y las limitaciones.
- Al entregar un cambio, explicar brevemente qué se modificó, cómo se verificó y qué queda pendiente. No declarar pruebas que no se ejecutaron.

## Documentación académica

Al trabajar en el informe, conservar su estructura: introducción; identificación del problema; levantamiento de requerimientos; marco teórico; objetivos; metodología; arquitectura TI; arquitectura empresarial; conclusiones; referencias y anexos.

- Mantener trazabilidad entre problema, evidencia, objetivos, requerimientos, solución y validación.
- Identificar las cifras de encuestas y presupuestos como datos reportados por el documento; no inventar respuestas, mediciones, citas ni resultados de pruebas.
- Verificar referencias bibliográficas antes de usarlas como evidencia externa.
- Separar resultados obtenidos, metas y trabajo futuro. Actualizar el índice y retirar instrucciones de plantilla al preparar la entrega final.

## Ambigüedades que deben resolverse al abordar cada área

- **Identidad de menores:** el informe prohíbe el registro directo de menores, pero también describe cuentas estudiantiles con correo institucional y un formulario genérico con nombre, correo y contraseña. Definir quién provisiona las cuentas, los datos mínimos y la autorización correspondiente antes de implementar ese flujo.
- **Privacidad y seguimiento:** conciliar la afirmación de no almacenar información privada con la persistencia de correo y progreso. Un correo institucional también puede identificar a una persona.
- **Carga de archivos y Godot:** la restricción de HTML de usuarios debe coexistir con el despliegue controlado de actividades HTML5/WASM; no habilitar cargas ejecutables arbitrarias para resolver esa diferencia.
- **Suscripciones:** una historia de eliminación de cuenta menciona cancelarlas, pero el alcance no define pagos ni un modelo comercial. No incorporar facturación basándose solo en esa mención.
- **Persistencia de archivos:** el informe describe guardar archivos en base de datos y también recursos en almacenamiento cloud. Definir la separación entre metadatos y binarios antes de implementar las cargas.
- **Normativa:** el documento contiene numeración inconsistente de la Ley TEA en una sección. Verificar la referencia oficial al actualizar el informe.

Resolver las ambigüedades que afecten al trabajo solicitado y registrar la decisión. Continuar con las tareas independientes sin asumir resueltas las decisiones pendientes.
