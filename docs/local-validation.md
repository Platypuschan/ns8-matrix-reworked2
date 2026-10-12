# Prüfstand vom 12.10.2026

Die Grundimplementierung enthält Synapse, Element Web, PostgreSQL, LDAP/AD, Shared Secret Auth, die ausgewählten Bridges/Bots, Ketesa, coturn/MatrixRTC, NS8-UI, Backup/Restore und Wartung.

Bestanden: 38 Unit-Tests, Python-/JSON-/Shell-Prüfung, UI-Lint und UI-Produktionsbuild. Die Tests überprüfen unter anderem Token-/Namespace-Isolation, LDAP/SMTP-Konfiguration, die NS8-Portbereichsvariablen, Portwechsel, Idempotenz, Firewall-Deaktivierung, maubot-Defaults für das verwendete Image, aktuelle und ältere Matrix-Raum-IDs, Bridge-/Bot-Startvoraussetzungen, Snapshot-Fehlerbehandlung und Wiederanlauf-Reihenfolge, vollständigen Datenersatz beim Restore und die sichere Speicherung bei erfolgreicher oder fehlgeschlagener Passwortrotation.

Die GitHub-Validierung, beide Runtime-Images und das NS8-Modul sind erfolgreich gebaut. Die vollständigen NS8-QEMU-Integrationstests sind unter Debian 13 und Rocky Linux 9 bestanden. Geprüfter Code-Commit: `af4b1b767233eddd355436e2039ce4fcc7abacf2`. [CI-Ergebnis](https://github.com/Platypuschan/ns8-matrix-reworked2/actions/runs/38299754524).

Die VM-Tests bestätigen Synapse-API und Discovery, öffentliche und interne Login-Adressen, lokalen Administrator-Login, unveränderte Konfiguration ohne Neustart, maubot/Ketesa-HTTP, Ablehnung ungültiger Einstellungen, alle Bridge-/Bot-Starts und die Synchronisation der fünf mautrix-Bots. Snapshot und Restore bewahren Datenbank, Plugin-Daten, Anmeldedaten und Signaturschlüssel; nach dem Backup hinzugefügte Tabellen und Dateien werden entfernt. coturn, LiveKit und JWT starten, RTC-Discovery ist verfügbar. Deaktivierung, Firewall-Portentfernung, Passwortrotation und Modul-Entfernung sind ebenfalls geprüft.

Noch offen: reale Remote-Konto-Logins und Anrufe über NAT. Hookshot-Verschlüsselung mit einer externen Redis-Instanz und reale LDAP-/Smarthost-Verbindungen benötigen passende zusätzliche Testsysteme.

Die GitHub-Workflows bauen die beiden eigenen Runtime-Images und das NS8-Modul, danach folgen Integrationstests unter Rocky Linux 9 und Debian 13. Lokale Tests allein ersetzen diese Laufzeitprüfung nicht.

Es wurde keine stabile Version veröffentlicht und kein produktiver Rollout ausgeführt.
