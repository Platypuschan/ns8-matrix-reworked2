# Lokaler Prüfstand vom 12.10.2026

Die Grundimplementierung enthält Synapse, Element Web, PostgreSQL, LDAP/AD, Shared Secret Auth, die ausgewählten Bridges/Bots, Ketesa, coturn/MatrixRTC, NS8-UI, Backup/Restore und Wartung.

Bestanden: 27 Unit-Tests, Python-/JSON-/Shell-Prüfung, UI-Lint und UI-Produktionsbuild. Die Tests überprüfen unter anderem Token-/Namespace-Isolation, LDAP/SMTP-Konfiguration, Portwechsel, Idempotenz, Snapshot-Fehlerbehandlung und die sichere Speicherung bei erfolgreicher oder fehlgeschlagener Passwortrotation.

Noch offen: reale Image-Builds, NS8-QEMU-Integrationstests, Remote-Konto-Logins und Anrufe über NAT. Die Workflows und Tests dafür sind vorbereitet.

Die GitHub-Workflows bauen die beiden eigenen Runtime-Images und das NS8-Modul, danach folgen Integrationstests unter Rocky Linux 9 und Debian 13. Ein bestandener lokaler Teststand ersetzt diese Laufzeitprüfung nicht. Reale Bridge-Konten und Anrufe über NAT benötigen zusätzliche Prüfungen mit passenden Konten und Netzwerkbedingungen.

Es wurde keine stabile Version veröffentlicht und kein produktiver Rollout ausgeführt.
