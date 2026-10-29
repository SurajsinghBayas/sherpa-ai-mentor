# Sherpa AI for Android and iOS

The mobile apps wrap the web app (`apps/web`) with [Capacitor 8](https://capacitorjs.com), the way
`apps/desktop` wraps it with Tauri. The screens are the web app's own, so there is one UI to keep in
step. The app adds the pieces a phone needs:
- the header clears the status bar and notch (`--safe-top` in `globals.css`)
- the status bar icons follow the theme
- the app opens straight into the workspace
- links to other sites open in the browser
- voice mode can use the microphone

Sign-in uses the email code or a password. Google and GitHub only return to web addresses, so
the apps hide those buttons, as the desktop app does.

## API address

The web export is built against `SHERPA_API_URL`, which defaults to the production site
(`https://sherpa-ai.tech`, where nginx passes `/api` to the API). To point at another server:

```bash
SHERPA_API_URL=https://api.example.com npm run sync
```

The API must allow the apps' origins: `http://localhost` (Android) and `capacitor://localhost`
(iOS). Both are in the default `DESKTOP_ORIGINS`, so they need nothing in `.env` unless you set
`DESKTOP_ORIGINS` there yourself.

## Android

You need:
- **JDK 21.**
- **The Android SDK**, with platform 36 and build-tools 36. Android Studio installs both.
- **`ANDROID_HOME`** pointing at the SDK.

```bash
npm install
npm run android        # build the web export, sync, and run on the connected phone
npm run android:apk    # or just build android/app/build/outputs/apk/debug/app-debug.apk
```

To prepare the phone:
1. Turn on **Developer options**: tap Settings → About phone → Build number seven times.
2. In Developer options, turn on **USB debugging**.
3. Plug the phone in and accept the "Allow USB debugging?" prompt.
4. Check that `adb devices` lists the phone.

## iOS

You need full Xcode (from the App Store), not just the command-line tools.

```bash
npm install
npm run ios            # build the web export, sync, and open the Xcode project
```

Then, in Xcode:
1. Pick your team under **Signing & Capabilities**.
2. Choose your iPhone or a simulator.
3. Press Run.

Capacitor 8 uses Swift Package Manager, so CocoaPods isn't needed.

## Icons and splash screens

`npm run icons` draws them from `apps/desktop/icons/app-icon.png`:
- **Icons:** the pixel mascot on Sherpa blue, including the Android adaptive and round icons and
  the iOS 1024 px icon.
- **Splash screens:** the mascot on the paper background.

## How navigation works inside the app

The apps serve `index.html` for any path without a file extension. Moving between pages inside
the app works normally, because those moves use client-side routing. A full page load of a deep
link like `/login` would show the start page instead. So when a session expires, the app reloads
at `/`, and the app routes a signed-out user to sign-in from there (`signInAgain` in `lib/api.ts`).
