# SoSoja Mobile

Une application Android minimaliste servant de wrapper pour le site https://www.sosoja.com.

## Prérequis
- Flutter SDK installé sur votre machine.
- Un émulateur Android ou un appareil physique branché.

## Comment compiler l'APK
1. Ouvrez un terminal dans le dossier `sosoja_mobile`.
2. Assurez-vous que les dépendances sont téléchargées :
   ```bash
   flutter pub get
   ```
3. Générez l'APK :
   ```bash
   flutter build apk --release
   ```
L'APK sera disponible dans `build/app/outputs/flutter-apk/app-release.apk`.

## Configuration technique
- **Package Name :** `com.sosoja.app`
- **Technologie :** Flutter + `webview_flutter`
- **URL cible :** `https://www.sosoja.com`
- **SDK Min :** 21 (Android 5.0)
