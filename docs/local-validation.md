# Lokaler Prüfstand vom 12.10.2026

Die Grundimplementierung enthält Synapse, Element Web, PostgreSQL, LDAP/AD, Shared Secret Auth, die ausgewählten Bridges/Bots, Ketesa, coturn/MatrixRTC, NS8-UI, Backup/Restore und Wartung.

Bestanden: 38 Unit-Tests, Python-/JSON-/Shell-Prüfung, UI-Lint und UI-Produktionsbuild. Die Tests überprüfen unter anderem Token-/Namespace-Isolation, LDAP/SMTP-Konfiguration, die NS8-Portbereichsvariablen, Portwechsel, Idempotenz, Firewall-Deaktivierung, maubot-Defaults für das verwendete Image, aktuelle und ältere Matrix-Raum-IDs, Bridge-/Bot-Startvoraussetzungen, Snapshot-Fehlerbehandlung und Wiederanlauf-Reihenfolge, vollständigen Datenersatz beim Restore und die sichere Speicherung bei erfolgreicher oder fehlgeschlagener Passwortrotation.

Die beiden Runtime-Images und das NS8-Modul werden in GitHub erfolgreich gebaut und veröffentlicht. Die NS8-QEMU-Tests haben Synapse-API und Discovery, öffentliche und interne Login-Adressen, den lokalen Administrator-Login, unveränderte Konfiguration ohne Neustart sowie die HTTP-Server von maubot und Ketesa bestätigt. Alle ausgewählten Bridges/Bots starten mit den erzeugten Konfigurationen; die fünf mautrix-Bots können mit Synapse synchronisieren. Der Snapshot wurde erstellt.

Noch offen: vollständige NS8-QEMU-Integrationstests einschließlich Wiederanlauf, Restore und RTC, Remote-Konto-Logins und Anrufe über NAT.

Die GitHub-Workflows bauen die beiden eigenen Runtime-Images und das NS8-Modul, danach folgen Integrationstests unter Rocky Linux 9 und Debian 13. Ein bestandener lokaler Teststand ersetzt diese Laufzeitprüfung nicht. Reale Bridge-Konten und Anrufe über NAT benötigen zusätzliche Prüfungen mit passenden Konten und Netzwerkbedingungen.

Es wurde keine stabile Version veröffentlicht und kein produktiver Rollout ausgeführt.
