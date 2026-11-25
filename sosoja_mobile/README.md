# SoSoja Mobile

Une application Flutter pour Android, iPhone et iPad qui ouvre SoSoja dans une WebView.

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

## Tester sur iOS

Sur un Mac équipé de Flutter, Xcode avec un simulateur iOS et CocoaPods, lancez ces commandes depuis `sosoja_mobile` :

```bash
flutter pub get
open -a Simulator
flutter devices
flutter run -d <identifiant-du-simulateur>
```

## Tester sur un iPad ou un iPhone physique

Lancez Odoo avec Docker sur le Mac et connectez les deux appareils au même réseau. Dans **Réglages Système → Général → Partage** sur le Mac, relevez son nom d’hôte local en `.local`. Sur l’iPad, vérifiez dans Safari que l’adresse `http://nom-du-mac.local:8069/soja` ouvre Odoo.

Ouvrez `ios/Runner.xcworkspace` après l’installation des dépendances iOS et sélectionnez votre équipe Apple dans **Signing & Capabilities**. Le bundle ID par défaut est `com.sosoja.app`. Lancez ensuite l’application en remplaçant le nom d’hôte et l’identifiant de l’iPad :

```bash
flutter run -d <identifiant-ipad> --dart-define=SOSOJA_URL=http://nom-du-mac.local:8069/soja
```

Sur l’iPad, autorisez SoSoja à accéder au réseau local lorsqu’iPadOS le demande. Le simulateur iOS utilise par défaut `http://localhost:8069/soja`.

## Configuration technique
- **Package Name :** `com.sosoja.app`
- **Technologie :** Flutter + `webview_flutter`
- **URL cible :** `https://www.sosoja.com`
- **SDK Min :** 21 (Android 5.0)
