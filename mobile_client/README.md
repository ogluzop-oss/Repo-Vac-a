# Smart Manager · Cliente móvil (React Native)

Cliente móvil **offline-first** en **React Native + TypeScript** que consume **exclusivamente** la
REST API oficial de Smart Manager (`/api/v1`) servida por el backend Flask del proyecto de escritorio.

> Este cliente **materializa** los contratos que ya existían modelados en el servidor
> (`src/services/mobile/`): `core.py` (catálogo de capacidades → endpoints), `networking.py`
> (cliente REST con JWT Bearer) y `sync.py` (cola `Outbox` + resolución de conflictos offline-first).
> No inventa un segundo backend ni habla con la base de datos directamente: **todo pasa por REST**.

---

## 1. Requisitos

- **Node.js ≥ 18** y npm.
- Entorno React Native configurado (**RN 0.75**): JDK 17 + Android SDK para Android; Xcode + CocoaPods
  para iOS. Guía oficial: <https://reactnative.dev/docs/environment-setup> ("React Native CLI").
- El **backend Flask** de Smart Manager corriendo y accesible desde el dispositivo/emulador.

## 2. Instalación

```bash
cd mobile_client
npm install            # instala dependencias JS
# iOS únicamente:
cd ios && pod install && cd ..
```

> Las carpetas nativas `android/` e `ios/` **no** se incluyen en el repositorio (`.gitignore`). Este
> paquete es la capa JS/TS. Para generar los proyectos nativos usa la plantilla oficial de RN 0.75 y
> copia `src/`, o ejecuta `npx @react-native-community/cli init` con el mismo `name` de `app.json`
> (`SmartManagerMobile`) y añade las dependencias del `package.json`.

## 3. Configurar la conexión con la API de escritorio

La app habla con el backend Flask (`/api/v1`). Ajusta el host en **`src/config/env.ts`**
(`API_HOST`). Ver también `.env.example`:

| Entorno              | `API_HOST` recomendado          | Motivo                                   |
| -------------------- | ------------------------------- | ---------------------------------------- |
| Emulador Android     | `http://10.0.2.2:5000`          | `10.0.2.2` = "localhost" del PC anfitrión |
| Emulador iOS         | `http://127.0.0.1:5000`         | Comparte red con el host                  |
| Dispositivo físico   | `http://<IP-LAN-de-tu-PC>:5000` | El móvil sale por la red local            |

Para dispositivo físico, arranca el backend escuchando en `0.0.0.0` y abre el puerto en el firewall.
Android bloquea HTTP en claro por defecto: en desarrollo se permite vía `usesCleartextTraffic` (o usa
HTTPS). En producción, **siempre HTTPS**.

## 4. Ejecutar en desarrollo

```bash
npm start              # arranca Metro
# en otra terminal:
npm run android        # compila y lanza en Android
npm run ios            # compila y lanza en iOS
```

Comprobaciones útiles:

```bash
npm run tsc            # type-check (sin emitir)
npm test               # pruebas (incluye la paridad de resolución de conflictos con sync.py)
```

## 5. Cómo se comunica con la API

```
LoginScreen ─▶ api/auth.login ─┐
                               ├─ POST /api/v1/auth/login  {usuario, password, id_empresa?}
                               │     ├─ 200 {access, refresh, empresa, usuario}
                               │     ├─ 200 {mfa_required, mfa_token}  ─▶ POST /api/v1/auth/mfa {mfa_token, codigo}
                               │     └─ 401 {error:"invalid_credentials"}
                               ▼
                   tokenStore (AsyncStorage)  ── access + refresh
                               ▼
   api/client.request(metodo, ruta) ── Authorization: Bearer <access>
                               │
                               ├─ 401 ▶ POST /api/v1/auth/refresh {refresh} ▶ reintento único
                               ▼
                     REST /api/v1/*  (system/health, stock, orders, …)
```

- **`src/api/client.ts`** — espejo de `networking.py`: `request(metodo, ruta, {params, cuerpo})` →
  `{status, json}`, cabecera `Authorization: Bearer`, y **refresh automático** del access token ante
  un 401 (reintenta una vez).
- **`src/api/auth.ts`** — login, verificación MFA y logout según `routers/auth.py`.
- **`src/api/capabilities.ts`** — catálogo capacidad→endpoint, espejo de `core.py`; alimenta el menú
  del Dashboard.

## 6. Offline-first (Outbox en SQLite)

- **`src/db/database.ts`** abre la BD local `smartmanager.db` y crea la tabla `outbox`.
- **`src/db/sync.ts`** implementa la clase **`Outbox`** (persistida) con la misma API que `sync.py`:
  `encolar / pendientes / marcar / sincronizar`. Las operaciones creadas sin conexión se guardan y se
  envían luego con **idempotencia** (`_idem` en el cuerpo + cabecera `Idempotency-Key`).
- **`src/db/conflict.ts`** porta 1:1 `resolver_conflicto` y `ESTRATEGIAS`
  (`ultimo_gana`/`servidor_gana`/`cliente_gana`/`manual`).

Flujo de prueba: en la pantalla **Escaneo**, cada lectura (cámara o entrada manual) se **encola** en el
Outbox; desde el **Dashboard**, "Sincronizar" las envía a `/api/v1/stock`.

## 7. Escaneo de códigos de barras

`src/components/CameraScanner.tsx` usa **react-native-vision-camera** (v4). Requiere permisos nativos:

- **Android** (`android/app/src/main/AndroidManifest.xml`): `<uses-permission android:name="android.permission.CAMERA" />`
- **iOS** (`ios/<App>/Info.plist`): `NSCameraUsageDescription`.

Si el módulo nativo no está enlazado, la pantalla **degrada** automáticamente a la entrada manual
(gracias a un `ErrorBoundary`), de modo que el flujo offline-first se puede probar sin hardware.

## 8. Estructura

```
mobile_client/
├─ index.js                 # registro del componente raíz
├─ app.json                 # nombre de la app (SmartManagerMobile)
├─ src/
│  ├─ App.tsx               # providers + init de la BD local
│  ├─ config/env.ts         # API_HOST / API_BASE_URL
│  ├─ api/
│  │  ├─ client.ts          # HTTP + Bearer + refresh (↔ networking.py)
│  │  ├─ auth.ts            # login / MFA / logout (↔ routers/auth.py)
│  │  ├─ tokenStore.ts      # persistencia de tokens
│  │  └─ capabilities.ts    # capacidad→endpoint (↔ core.py)
│  ├─ db/
│  │  ├─ database.ts        # SQLite (tabla outbox)
│  │  ├─ sync.ts            # Outbox persistido (↔ sync.py)
│  │  └─ conflict.ts        # resolución de conflictos (puro, testeable)
│  ├─ store/AuthContext.tsx # estado de sesión
│  ├─ navigation/           # RootNavigator + tipos
│  ├─ screens/              # Login · Dashboard · Scanner
│  ├─ components/           # CameraScanner
│  └─ theme/colors.ts       # paleta (dark + cian, marca del escritorio)
└─ __tests__/conflict.test.ts
```

## 9. Estado y notas de honestidad

- **Es un andamiaje inicial (MVP), no una app terminada.** El código está escrito para compilar y
  ejecutarse tras `npm install` + configuración nativa, pero **no se ha construido/lanzado dentro de
  este repositorio** (aquí solo se generó el scaffold).
- Pantallas reales implementadas: **Login (con MFA), Dashboard (capacidades + sincronización) y
  Scanner**. El resto de capacidades del menú aún **no** tienen pantalla dedicada (abrir stock lleva
  al escáner como demostración).
- **Seguridad**: los tokens se guardan en `AsyncStorage` por simplicidad del MVP. Para producción,
  migrar a almacenamiento seguro (`react-native-keychain` / Keystore / Keychain) y forzar HTTPS.
- Los endpoints del catálogo (`/orders`, `/stock`, …) deben existir en el backend; si alguno no está
  implementado, la llamada devolverá 404 y la UI lo reflejará.
