import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SoSojaApp());
}

class SoSojaApp extends StatelessWidget {
  const SoSojaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SoSoja',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.green,
      ),
      home: const BrowserPage(),
    );
  }
}

class BrowserPage extends StatefulWidget {
  const BrowserPage({super.key});

  @override
  State<BrowserPage> createState() => _BrowserPageState();
}

class _BrowserPageState extends State<BrowserPage> {
  static const _configuredUrl = String.fromEnvironment('SOSOJA_URL');
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    final defaultUrl = defaultTargetPlatform == TargetPlatform.iOS
        ? 'http://localhost:8069/soja'
        : 'https://www.sosoja.com';
    final url = _configuredUrl.isEmpty ? defaultUrl : _configuredUrl;
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {
            // Update loading bar.
          },
          onPageStarted: (String url) {},
          onPageFinished: (String url) {},
          onWebResourceError: (WebResourceError error) {},
          onNavigationRequest: (NavigationRequest request) {
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(url));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // WillPopScope is deprecated in newer Flutter, but PopScope is for Flutter 3.12+
      // Using a simple logic for now.
      body: SafeArea(
        child: PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, result) async {
            if (didPop) return;
            if (await _controller.canGoBack()) {
              await _controller.goBack();
            } else {
              // If we can't go back, we let the system handle it (exit)
              if (context.mounted) {
                Navigator.of(context).pop();
              }
            }
          },
          child: WebViewWidget(controller: _controller),
        ),
      ),
    );
  }
}
